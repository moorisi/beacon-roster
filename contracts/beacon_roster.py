# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from datetime import datetime, timezone
from hashlib import sha256
import json
import re


CHAIN = '52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971'
RELAYS = ('https://api.drand.sh', 'https://drand.cloudflare.com')
GENESIS = 1692803367
PERIOD = 3
DRAW_DELAY = 180
LABEL = r'[A-Za-z0-9_-]{1,24}'


def fail(message):
    raise gl.vm.UserError(message)


def now_seconds():
    delta = datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400 + delta.seconds


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key')
        obj[key] = value
    return obj


def parse(text, reason):
    try:
        return json.loads(text, object_pairs_hook=unique_keys)
    except ValueError:
        fail(reason)


def encode(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def labels(values):
    return (isinstance(values, list) and 2 <= len(values) <= 10 and
            all(isinstance(value, str) and re.fullmatch(LABEL, value) for value in values) and
            len(set(values)) == len(values))


def roster_from(text):
    if not text.startswith('br1:') or len(text) > 4096:
        fail('Invalid roster')
    roster = parse(text[4:], 'Invalid roster')
    if not isinstance(roster, dict) or set(roster) != {'tasks', 'reviewers', 'eligible'}:
        fail('Invalid roster')
    tasks, reviewers, eligible = roster['tasks'], roster['reviewers'], roster['eligible']
    if not labels(tasks) or not labels(reviewers) or len(tasks) != len(reviewers):
        fail('Provide equal numbers of distinct tasks and reviewers')
    if not isinstance(eligible, dict) or set(eligible) != set(tasks):
        fail('Provide eligibility for every task')
    for row in eligible.values():
        if (not isinstance(row, list) or not 1 <= len(row) <= len(reviewers) or
                any(not isinstance(value, str) or value not in reviewers for value in row) or
                len(set(row)) != len(row)):
            fail('Invalid eligible reviewer list')
    return {'tasks': sorted(tasks), 'reviewers': sorted(reviewers),
            'eligible': {task: sorted(row) for task, row in eligible.items()}}


def options(roster):
    reviewers = {reviewer: 1 << ix for ix, reviewer in enumerate(roster['reviewers'])}
    return [[reviewers[reviewer] for reviewer in roster['eligible'][task]] for task in roster['tasks']]


def counter(rows):
    memo = {}

    def count(task, remaining):
        if task == len(rows):
            return 1
        key = (task, remaining)
        if key not in memo:
            memo[key] = sum(count(task + 1, remaining ^ bit) for bit in rows[task] if remaining & bit)
        return memo[key]

    return count


def count_matchings(roster):
    rows = options(roster)
    return counter(rows)(0, (1 << len(rows)) - 1)


def unrank(roster, rank):
    rows = options(roster)
    count = counter(rows)
    remaining = (1 << len(rows)) - 1
    assignment = {}
    for task, row in enumerate(rows):
        for bit in row:
            if remaining & bit:
                completions = count(task + 1, remaining ^ bit)
                if rank < completions:
                    reviewer = roster['reviewers'][bit.bit_length() - 1]
                    assignment[roster['tasks'][task]] = reviewer
                    remaining ^= bit
                    break
                rank -= completions
        else:
            fail('Assignment rank invariant')
    return assignment


def read_round(relay, round_number):
    response = gl.nondet.web.get(f'{relay}/{CHAIN}/public/{round_number}')
    if response.status != 200 or not 1 <= len(response.body) <= 4096:
        fail('Beacon round unavailable')
    try:
        text = response.body.decode('utf-8')
    except UnicodeError:
        fail('Invalid beacon response')
    value = parse(text, 'Invalid beacon response')
    if not isinstance(value, dict) or type(value.get('round')) is not int or value['round'] != round_number:
        fail('Beacon round mismatch')
    signature, randomness = value.get('signature'), value.get('randomness')
    if (not isinstance(signature, str) or not re.fullmatch(r'[0-9a-f]{96}', signature) or
            not isinstance(randomness, str) or sha256(bytes.fromhex(signature)).hexdigest() != randomness):
        fail('Beacon digest mismatch')
    return {'round': round_number, 'signature': signature, 'randomness': randomness}


def observe(round_number):
    def read():
        first, second = [read_round(relay, round_number) for relay in RELAYS]
        if first != second:
            fail('Beacon relays disagree')
        return first

    def verify(proposal):
        try:
            independent = read()
        except gl.vm.UserError as error:
            return not isinstance(proposal, gl.vm.Return) and getattr(proposal, 'message', None) == error.message
        except Exception:
            return False
        return isinstance(proposal, gl.vm.Return) and encode(proposal.calldata) == encode(independent)

    return gl.vm.run_nondet_unsafe(read, verify)


def sample_rank(randomness, roster_digest, round_number, count):
    ceiling = 1 << 256
    cutoff = ceiling - ceiling % count
    material = (b'BeaconRoster-v1\0' + round_number.to_bytes(8, 'big') +
                bytes.fromhex(roster_digest) + bytes.fromhex(randomness))
    for retry in range(32):
        candidate = int.from_bytes(sha256(material + bytes([retry])).digest(), 'big')
        if candidate < cutoff:
            return candidate % count
    fail('No sample in hash budget')


class BeaconRoster(gl.Contract):
    roster: str
    round_number: u64
    sealed_at: u64
    matchings: u64
    result: str

    def __init__(self, roster: str):
        canonical = roster_from(roster)
        count = count_matchings(canonical)
        if count == 0:
            fail('No complete eligible assignment')
        sealed = now_seconds()
        if sealed < GENESIS:
            fail('Transaction time before beacon genesis')
        self.roster = encode(canonical)
        self.matchings = u64(count)
        self.sealed_at = u64(sealed)
        self.round_number = u64(1 + (sealed + DRAW_DELAY - GENESIS + PERIOD - 1) // PERIOD)
        self.result = ''

    def _available_at(self):
        return GENESIS + (int(self.round_number) - 1) * PERIOD

    @gl.public.write
    def draw(self) -> None:
        if self.result:
            fail('Assignment already drawn')
        if now_seconds() < self._available_at():
            fail('Beacon round not due')
        round_number = int(self.round_number)
        beacon = observe(round_number)
        rank = sample_rank(beacon['randomness'], sha256(self.roster.encode()).hexdigest(),
                           round_number, int(self.matchings))
        self.result = encode({'beacon': beacon, 'rank': rank, 'assignment': unrank(json.loads(self.roster), rank)})

    @gl.public.view
    def get_state(self) -> dict:
        return {'roster': json.loads(self.roster), 'roster_sha256': sha256(self.roster.encode()).hexdigest(),
                'matchings': int(self.matchings), 'sealed_at': int(self.sealed_at),
                'round': int(self.round_number), 'available_at': self._available_at(),
                'result': json.loads(self.result) if self.result else None}

    @gl.public.view
    def assignment_at(self, rank: int) -> dict:
        if type(rank) is not int or not 0 <= rank < int(self.matchings):
            fail('Invalid assignment rank')
        return unrank(json.loads(self.roster), rank)
