from datetime import datetime, timezone
from hashlib import sha256
from itertools import permutations
import json
import re

import pytest


GENESIS = 1692803367
SEALED = 1760000000
CHAIN = '52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971'
RELAYS = ('https://api.drand.sh', 'https://drand.cloudflare.com')
ROSTER = {
    'tasks': ['paper-C', 'paper-A', 'paper-B'],
    'reviewers': ['carol', 'alice', 'bob'],
    'eligible': {'paper-C': ['carol', 'alice', 'bob'],
                 'paper-A': ['carol', 'bob'], 'paper-B': ['alice', 'bob']}
}


def warp(vm, seconds):
    vm.warp(datetime.fromtimestamp(seconds, timezone.utc).isoformat())


def deploy(vm, direct_deploy, roster=ROSTER):
    warp(vm, SEALED)
    return direct_deploy('contracts/beacon_roster.py', 'br1:' + json.dumps(roster), sdk_version='v0.2.16')


def beacon(round_number, byte):
    sig = bytes([byte]) * 48
    return {'round': round_number, 'signature': sig.hex(), 'randomness': sha256(sig).hexdigest()}


def mock(vm, round_number, first, second, status=200):
    vm.clear_mocks()
    for relay, payload in zip(RELAYS, (first, second)):
        vm.mock_web(re.escape(f'{relay}/{CHAIN}/public/{round_number}'),
                    {'status': status, 'body': json.dumps(payload).encode()})


def enumerate_assignments(roster):
    tasks = sorted(roster['tasks'])
    assignments = []
    for reviewers in permutations(sorted(roster['reviewers'])):
        result = dict(zip(tasks, reviewers))
        if all(result[task] in roster['eligible'][task] for task in tasks):
            assignments.append(result)
    return assignments


def test_rank_bijection_and_early_draw(direct_vm, direct_deploy):
    contract = deploy(direct_vm, direct_deploy)
    state = contract.get_state()
    assert state['sealed_at'] == SEALED
    assert SEALED + 180 <= state['available_at'] < SEALED + 183
    assert state['available_at'] == GENESIS + (state['round'] - 1) * 3
    assert state['result'] is None
    expected = enumerate_assignments(ROSTER)
    assert [contract.assignment_at(i) for i in range(state['matchings'])] == expected
    with direct_vm.expect_revert('Invalid assignment rank'):
        contract.assignment_at(len(expected))
    with direct_vm.expect_revert('Beacon round not due'):
        contract.draw()
    assert contract.get_state() == state


@pytest.mark.parametrize('seed_byte', [3, 9, 27])
def test_future_beacon_controls_draw(direct_vm, direct_deploy, direct_bob, seed_byte):
    contract = deploy(direct_vm, direct_deploy)
    initial = contract.get_state()
    value = beacon(initial['round'], seed_byte)
    mock(direct_vm, initial['round'], value, value)
    warp(direct_vm, initial['available_at'])
    direct_vm.sender = direct_bob
    contract.draw()
    material = (b'BeaconRoster-v1\0' + initial['round'].to_bytes(8, 'big') +
                bytes.fromhex(initial['roster_sha256']) + bytes.fromhex(value['randomness']))
    rank = int(sha256(material + bytes([0])).hexdigest(), 16) % initial['matchings']
    expected = {'rank': rank, 'beacon': value, 'assignment': enumerate_assignments(ROSTER)[rank]}
    assert contract.get_state()['result'] == expected
    assert direct_vm.run_validator() is True
    other = beacon(initial['round'], seed_byte + 1)
    assert direct_vm.run_validator(leader_result=other) is False
    mock(direct_vm, initial['round'], other, other)
    assert direct_vm.run_validator() is False
    with direct_vm.expect_revert('Assignment already drawn'):
        contract.draw()
    assert contract.get_state()['result'] == expected


@pytest.mark.parametrize('case', ['unavailable', 'round', 'digest', 'disagree'])
def test_bad_observation_does_not_seal_result(direct_vm, direct_deploy, case):
    contract = deploy(direct_vm, direct_deploy)
    initial = contract.get_state()
    round_number = initial['round']
    value = beacon(round_number, 1)
    other = {
        'unavailable': value,
        'round': beacon(round_number+1, 1),
        'digest': {**value, 'randomness': '0' * 64},
        'disagree': beacon(round_number, 2)
    }[case]
    error = {'unavailable': 'Beacon round unavailable', 'round': 'Beacon round mismatch',
             'digest': 'Beacon digest mismatch', 'disagree': 'Beacon relays disagree'}[case]
    warp(direct_vm, initial['available_at'])
    mock(direct_vm, round_number, value, other, 404 if case == 'unavailable' else 200)
    with direct_vm.expect_revert(error):
        contract.draw()
    assert contract.get_state() == initial
    mock(direct_vm, round_number, value, value)
    contract.draw()
    assert contract.get_state()['result']['beacon'] == value


def test_hall_violation_blocks_deployment(direct_vm, direct_deploy):
    roster = {**ROSTER, 'eligible': {'paper-A': ['alice'], 'paper-B': ['alice'], 'paper-C': ['bob', 'carol']}}
    with direct_vm.expect_revert('No complete eligible assignment'):
        deploy(direct_vm, direct_deploy, roster)


def test_full_ten_by_ten_remains_bounded(direct_vm, direct_deploy):
    tasks = [f'T{i}' for i in range(10)]
    reviewers = [f'R{i}' for i in range(10)]
    roster = {'tasks': tasks, 'reviewers': reviewers, 'eligible': dict.fromkeys(tasks, reviewers)}
    contract = deploy(direct_vm, direct_deploy, roster)
    assert contract.get_state()['matchings'] == 3_628_800
    assert contract.assignment_at(0) == dict(zip(tasks, reviewers))
    assert contract.assignment_at(3_628_799) == dict(zip(tasks, reversed(reviewers)))
