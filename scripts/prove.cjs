const fs = require('node:fs');
const {createHash} = require('node:crypto');
const {assert, equal, sourceHash, invoke, read, rpc, receipt, receiptSummary, save, delay} = require('./transport.cjs');
const {decodeReceipt} = require('./receipt-calldata.cjs');

const chain = '52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971';
const relays = ['https://api.drand.sh', 'https://drand.cloudflare.com'];
const genesis = 1692803367;
const sha = value => createHash('sha256').update(value).digest('hex');
const roster = {
  tasks: ['abstract', 'benchmark', 'data', 'methods'],
  reviewers: ['amy', 'ben', 'cam', 'dev'],
  eligible: {
    abstract: ['amy', 'cam', 'dev'],
    benchmark: ['amy', 'ben'],
    data: ['ben', 'cam', 'dev'],
    methods: ['amy', 'cam']
  }
};
const argument = 'br1:' + JSON.stringify(roster);

function enumerate(tasks, rest, result = {}) {
  if (tasks.length === 0) return [result];
  const [task, ...tail] = tasks;
  return rest.filter(name => roster.eligible[task].includes(name)).flatMap(name =>
    enumerate(tail, rest.filter(other => other !== name), {...result, [task]: name})
  );
}

async function liveRound(round) {
  for (let retry = 0; retry < 5; retry++) {
    const responses = await Promise.allSettled(relays.map(async relay => {
      const response = await fetch(relay + '/' + chain + '/public/' + round, {signal: AbortSignal.timeout(15000)});
      assert(response.ok, 'Relay error ' + response.status);
      const {round: number, signature, randomness} = await response.json();
      assert(number === round && /^[0-9a-f]{96}$/.test(signature) && sha(Buffer.from(signature, 'hex')) === randomness,
        'Invalid public round');
      return {round: number, signature, randomness};
    }));
    if (responses.every(response => response.status === 'fulfilled') && equal(responses[0].value, responses[1].value)) {
      return responses[0].value;
    }
    await delay(4000);
  }
  throw Error('Two relays did not return the same round');
}

function sample(state, beacon, count) {
  const round = Buffer.alloc(8);
  round.writeBigUInt64BE(BigInt(beacon.round));
  const prefix = Buffer.concat([Buffer.from('BeaconRoster-v1\0'), round,
    Buffer.from(state.roster_sha256, 'hex'), Buffer.from(beacon.randomness, 'hex')]);
  const space = 2n ** 256n;
  const total = BigInt(count);
  for (let counter = 0; counter < 32; counter++) {
    const candidate = BigInt('0x' + sha(Buffer.concat([prefix, Buffer.from([counter])])));
    if (space - candidate > space % total) return Number(candidate % total);
  }
  throw Error('No acceptable rank');
}

async function main() {
  const wallets = JSON.parse(process.env.ROSTER_ACCOUNTS || '[]');
  assert(wallets.length === 2 && wallets[0].address !== wallets[1].address, 'Two distinct wallets required');
  assert(await rpc('eth_chainId', []) === '0xf22f', 'StudioNet only');
  const code = fs.readFileSync('contracts/beacon_roster.py');
  const candidates = enumerate(roster.tasks, roster.reviewers);
  assert(candidates.length > 2 && candidates.length < 24, 'Need multiple constrained assignments');
  process.env.ROSTER_ACCOUNT = wallets[0].name;
  const deployment = await invoke('deploy', ['deploy', '--contract', 'contracts/beacon_roster.py', '--args', argument]);
  const deployed = await receipt('deploy', deployment, true);
  const contract = deployed.to_address || deployed.recipient;
  assert(/^0x[0-9a-f]{40}$/i.test(contract) && code.equals(Buffer.from(deployed.data.contract_code, 'base64')), 'Deployed source mismatch');
  const initial = await read('initial', ['call', contract, 'get_state']);
  assert(equal(initial.roster, roster) && initial.result === null && initial.matchings === candidates.length, 'Invalid initial roster');
  const canonical = JSON.stringify({eligible: roster.eligible, reviewers: roster.reviewers, tasks: roster.tasks});
  assert(initial.roster_sha256 === sha(canonical)
    && initial.available_at >= initial.sealed_at + 180 && initial.available_at < initial.sealed_at + 183
    && initial.available_at === genesis + (initial.round - 1) * 3, 'Invalid round commitment');

  const report = {contract, deployment, revision: process.env.GITHUB_SHA, source_sha256: sourceHash,
    relays, chain, candidate_count: candidates.length, trace: []};

  async function verify(label, raw, actor, args, expected, error) {
    assert((raw.from_address || raw.sender).toLowerCase() === wallets[actor].address
      && (raw.to_address || raw.recipient).toLowerCase() === contract.toLowerCase(), 'Wrong receipt addresses');
    assert(equal(await decodeReceipt(raw), args), 'Unexpected signed calldata');
    if (error) {
      const payload = Buffer.from(raw.consensus_data.leader_receipt[0].result, 'base64');
      assert(payload[0] === 1 && payload.subarray(1).toString() === error, 'Wrong expected error: ' + label);
    }
    const state = await read(label + '-state', ['call', contract, 'get_state']);
    assert(equal(state, expected), 'Unexpected state at ' + label);
    report.trace.push({label, ...receiptSummary(raw), signer: wallets[actor].address, args, error: error || null, state});
    save('progress', report);
  }
  await verify('deploy', deployed, 0, {args: [argument]}, initial);

  async function draw(label, actor, expected, error) {
    process.env.ROSTER_ACCOUNT = wallets[actor].name;
    const hash = await invoke(label, ['write', contract, 'draw']);
    await verify(label, await receipt(label, hash, !error), actor, {method: 'draw', args: []}, expected, error);
  }
  await draw('early', 1, initial, 'Beacon round not due');

  for (const [rank, expected] of candidates.entries()) {
    const result = await read('assignment-' + rank, ['call', contract, 'assignment_at', '--args', String(rank)]);
    assert(equal(result, expected), 'Onchain rank mapping differs');
  }
  const wait = Math.max(0, (initial.available_at + 8) * 1000 - Date.now());
  assert(wait <= 190000, 'Unexpected chain timestamp');
  if (wait) await delay(wait);
  const beacon = await liveRound(initial.round);
  const rank = sample(initial, beacon, candidates.length);
  const settled = {...initial, result: {beacon, rank, assignment: candidates[rank]}};
  report.independent = {beacon, candidates, rank};
  await draw('settle', 1, settled);
  await draw('redraw', 0, settled, 'Assignment already drawn');
  assert(code.equals(Buffer.from(await rpc('gen_getContractCode', [contract]), 'base64')), 'Fresh code mismatch');
  save('verified', report);
  console.log(JSON.stringify({contract, deployment, round: beacon.round, rank, result: settled.result.assignment}));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
