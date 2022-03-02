from brownie import DungeonManager, network, exceptions
from scripts.helpful_scripts import LOCAL_BLOCKAIN_ENVIRONMENTS, ZERO_ADDRESS, Gender, get_account, get_character, CharacterClass
from scripts.deploy import ARTIST_FEE, callback_with_randomness, deploy_dungeon_manager, deploy_fantasy
import pytest
from web3 import Web3


def test_create_dungeon_without_ether():
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    account = get_account()

    with pytest.raises(exceptions.VirtualMachineError):
        dm.createDungeon({"from": account, "value": 0})
    dungeon = dm.dungeons(account.address)
    assert_dungeon_doesnt_exists(dungeon)


def test_create_dungeon_with_ether():
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    account = get_account()
    treasure = Web3.toWei(1, "ether")

    tx = dm.createDungeon({"from": account, "value": treasure})

    assert tx.events["DungeonCreated"]["creator"] == account.address
    assert tx.events["DungeonCreated"]["treasure"] == treasure
    dungeon = dm.dungeons(account.address)
    assert dungeon[0] == account.address
    assert dungeon[1] == treasure

    assert_adventuring_party_is_empty(dungeon[2])


def test_create_dungeon_when_one_already_exists():
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    account = get_account()
    treasure = Web3.toWei(1, "ether")

    dm.createDungeon({"from": account, "value": treasure})

    with pytest.raises(exceptions.VirtualMachineError):
        dm.createDungeon({"from": account, "value": treasure})

    with pytest.raises(exceptions.VirtualMachineError):
        dm.createDungeon({"from": account, "value": 1})


def test_retire_dungeon_when_no_dungeon_active():
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    account = get_account()

    with pytest.raises(exceptions.VirtualMachineError):
        dm.retireDungeon({"from": account})


def test_retire_dungeon_when_dungeon_active():
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    account = get_account()
    treasure = Web3.toWei(1, "ether")
    dm.createDungeon({"from": account, "value": treasure})
    balance_before_retiring_dungeon = account.balance()

    tx = dm.retireDungeon({"from": account})

    assert tx.events["DungeonRetired"]["creator"] == account.address
    assert tx.events["DungeonRetired"]["treasure"] == treasure
    assert dm.balance() == 0
    # TODO better check by computing tx fee ?
    assert account.balance() > balance_before_retiring_dungeon

    assert_dungeon_doesnt_exists(dm.dungeons(account.address))


def test_start_dungeon_raid_without_tokens():
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    dungeon_creator = get_account(index=0)
    party_owner = get_account(index=1)
    treasure = Web3.toWei(1, "ether")
    dm.createDungeon({"from": dungeon_creator, "value": treasure})
    fantasy.setApprovalForAll(dm.address, True, {"from": party_owner})

    with pytest.raises(exceptions.VirtualMachineError):
        dm.startDungeonRaid(dungeon_creator.address, [], {"from": party_owner})


@pytest.mark.parametrize("tokens_count", [1, 2])
def test_start_dungeon_raid_with_tokens_with_no_chance_to_succeed(tokens_count):
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    dungeon_creator = get_account(index=0)
    party_owner = get_account(index=1)
    funding_account = get_account(index=2)
    funding_account.transfer(dungeon_creator, "50 ether")
    treasure = Web3.toWei(50 + tokens_count, "ether")
    dm.createDungeon({"from": dungeon_creator, "value": treasure})
    fantasy.setApprovalForAll(dm.address, True, {"from": party_owner})
    tx = fantasy.createCharacter({"from": party_owner, "value": ARTIST_FEE})
    tx.wait(1)
    callback_with_randomness(fantasy=fantasy, token_id=0, randomness=2222)

    with pytest.raises(exceptions.VirtualMachineError):
        dm.startDungeonRaid(dungeon_creator.address, [
                            0], {"from": party_owner})


@pytest.mark.parametrize("tokens_count", [1, 2, 10])
def test_start_dungeon_raid_with_tokens_with_chance_to_succeed(tokens_count):
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    dungeon_creator = get_account(index=0)
    party_owner = get_account(index=1)
    treasure = Web3.toWei(1, "ether")
    dm.createDungeon({"from": dungeon_creator, "value": treasure})
    fantasy.setApprovalForAll(dm.address, True, {"from": party_owner})
    token_ids = [i for i in range(tokens_count)]
    for token_id in range(tokens_count):
        tx = fantasy.createCharacter(
            {"from": party_owner, "value": ARTIST_FEE})
        tx.wait(1)
        callback_with_randomness(
            fantasy=fantasy, token_id=token_id, randomness=token_id)

    tx = dm.startDungeonRaid(dungeon_creator.address,
                             token_ids, {"from": party_owner})

    assert tx.events["DungeonRaidStarted"]["dungeonCreator"] == dungeon_creator.address
    assert tx.events["DungeonRaidStarted"]["partyOwner"] == party_owner.address
    assert tx.events["DungeonRaidStarted"]["tokenIds"] == token_ids
    dungeon = dm.dungeons(dungeon_creator.address)
    party = dungeon[2]
    print(f"party: {party}")
    assert party[0] == party_owner.address
    assert party[1] == token_ids
    assert party[2] == dm.getAventurersChanceToSucceed(token_ids, treasure)
    for token_id in token_ids:
        assert fantasy.ownerOf(token_id) == dm.address


@pytest.mark.parametrize("first_party_tokens_count", [1, 2])
@pytest.mark.parametrize("second_party_tokens_count", [1, 2])
def test_start_dungoen_raid_with_tokens_with_chance_to_succeed_when_dungeon_already_being_raided(first_party_tokens_count, second_party_tokens_count):
    if network.show_active() not in LOCAL_BLOCKAIN_ENVIRONMENTS:
        pytest.skip()
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    dungeon_creator = get_account(index=0)
    party_owner = get_account(index=1)
    second_party_owner = get_account(index=2)
    treasure = Web3.toWei(1, "ether")
    dm.createDungeon({"from": dungeon_creator, "value": treasure})
    for i in range(first_party_tokens_count):
        tx = fantasy.createCharacter(
            {"from": party_owner, "value": ARTIST_FEE})
        tx.wait(1)
        callback_with_randomness(fantasy=fantasy, token_id=i, randomness=i)
    for i in range(second_party_tokens_count):
        tx = fantasy.createCharacter(
            {"from": second_party_owner, "value": ARTIST_FEE})
        tx.wait(1)
        callback_with_randomness(
            fantasy=fantasy, token_id=i+second_party_tokens_count, randomness=i)
    fantasy.setApprovalForAll(dm.address, True, {"from": party_owner})
    fantasy.setApprovalForAll(dm.address, True, {"from": second_party_owner})

    dm.startDungeonRaid(dungeon_creator.address, [0], {"from": party_owner})
    with pytest.raises(exceptions.VirtualMachineError):
        dm.startDungeonRaid(dungeon_creator.address, [1], {
                            "from": second_party_owner})

# TODO test with high level tokens, to check that chance does nto exceed amx chance
@pytest.mark.parametrize("treasure_in_wei", [0.1, 1, 52, 100])
@pytest.mark.parametrize("tokens_count", [1, 2])
def test_get_adventurers_chance_to_succeed(treasure_in_wei, tokens_count):
    treasure = Web3.fromWei(treasure_in_wei, "ether")
    fantasy = deploy_fantasy()
    dm = deploy_dungeon_manager(fantasy_address=fantasy.address)
    party_owner = get_account(index=0)
    token_ids = [i for i in range(tokens_count)]
    for token_id in range(tokens_count):
        tx = fantasy.createCharacter(
            {"from": party_owner, "value": ARTIST_FEE})
        tx.wait(1)
        callback_with_randomness(
            fantasy=fantasy, token_id=token_id, randomness=token_id)
    chance = dm.getAventurersChanceToSucceed(token_ids, treasure)
    base_chance = dm.baseSuccessChancePerc()
    chance_without_treasure = base_chance + tokens_count
    expected = chance_without_treasure - \
        treasure if treasure < chance_without_treasure else 0
    assert chance == expected

# TODO: test if can send nfts to your own dungeon ? Do we allow it ? Or not ?


def assert_adventuring_party_is_empty(party):
    assert party[0] == ZERO_ADDRESS
    assert len(party[1]) == 0
    assert party[2] == 0


def assert_dungeon_doesnt_exists(dungeon):
    assert dungeon[0] == ZERO_ADDRESS
    assert dungeon[1] == 0
