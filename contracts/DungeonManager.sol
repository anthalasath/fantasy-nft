// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "@chainlink/contracts/src/v0.8/VRFConsumerBaseV2.sol";
import "@chainlink/contracts/src/v0.8/interfaces/VRFCoordinatorV2Interface.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";
import "./Fantasy.sol";
import "./Types.sol";
import "./FantasyUtils.sol";

// TODO: safeguard mechanism so that if VRF coord doesnt respond after x time (e.g 1 day), everyone can get their tokens and eth back
contract DungeonManager is VRFConsumerBaseV2, IERC721Receiver {
    using FantasyUtils for Dungeon;
    using FantasyUtils for DungeonReward[];
    using FantasyUtils for int256;

    mapping(address => Dungeon) public dungeons;
    mapping(uint256 => Dungeon) requestIdToDungeon;
    mapping(address => DungeonReward[]) public claimableRewards;

    Fantasy fantasy;

    VRFCoordinatorV2Interface COORDINATOR;
    bytes32 keyHash;
    uint32 callbackGasLimit = 100000;
    uint16 requestConfirmations = 3;
    uint64 subscriptionId;

    uint256 public constant maxSuccessChancePerc = 99;
    int256 public constant baseSuccessChancePerc = 50;

    event DungeonCreated(address indexed creator, uint256 treasure);
    event DungeonRetired(address indexed creator, uint256 treasure);
    event DungeonRaidStarted(
        address indexed dungeonCreator,
        address indexed partyOwner,
        uint256[] tokenIds
    );
    event DungeonRaidOutcome(
        address indexed dungeonCreator,
        address indexed partyOwner,
        uint256[] tokenIds,
        uint256 roll,
        bool success
    );

    constructor(
        address _fantasy,
        address _vrfCoordinator,
        bytes32 _keyHash,
        uint64 _subscriptionId
    ) VRFConsumerBaseV2(_vrfCoordinator) {
        fantasy = Fantasy(_fantasy);
        keyHash = _keyHash;
        COORDINATOR = VRFCoordinatorV2Interface(_vrfCoordinator);
        subscriptionId = _subscriptionId;
    }

    function createDungeon() public payable {
        require(
            dungeons[msg.sender].creator == address(0),
            "dungeon already exists"
        );
        require(msg.value > 0, "at least 1 WEI must be sent as treasure");

        dungeons[msg.sender] = Dungeon({
            creator: msg.sender,
            treasure: msg.value,
            adventuringParty: getEmptyAdventuringParty(),
            requestId: 0
        });

        emit DungeonCreated(msg.sender, msg.value);
    }

    function getEmptyAdventuringParty()
        internal
        pure
        returns (AdventuringParty memory)
    {
        uint256[] memory tokenIds = new uint256[](0);
        return
            AdventuringParty({
                owner: address(0),
                tokenIds: tokenIds,
                chanceToSucceed: 0
            });
    }

    function retireDungeon() public {
        require(
            dungeons[msg.sender].creator == msg.sender,
            "there is no dungeon belonging to this address"
        );
        require(
            !dungeons[msg.sender].isBeingRaided(),
            "there is currently a party inside this dungeon"
        );

        uint256 treasure = dungeons[msg.sender].treasure;
        delete dungeons[msg.sender];

        (bool sent, ) = msg.sender.call{value: treasure}("");
        require(sent, "failed to send treasure to creator");

        emit DungeonRetired(msg.sender, treasure);
    }

    function startDungeonRaid(address dungeonCreator, uint256[] memory tokenIds)
        public
    {
        // TODO need to check that a smart contract cannot create a dungeon unless it implements IERC721Receiver, same for an address entering a dungeon
        // else, it cannot receive the tokens if the dungeon wins.
        // TODO: Can someone do an attack by sending huge array or something ? I remember something about gas attacks. Wouldnt the transaction just
        // fail by running out of gas ?
        require(
            fantasy.isApprovedForAll(msg.sender, address(this)),
            "approval needed"
        );
        require(
            tokenIds.length > 0,
            "At least 1 token needs to be sent to the dungeon"
        );
        Dungeon storage dungeon = dungeons[dungeonCreator];
        require(
            !dungeon.isBeingRaided(),
            "some adventurers are already in this dungeon"
        );

        // Calculate upfront to avoid dungeon potentially being locked by out of gas when the randomness resolves;
        uint256 chanceToSucceed = getAventurersChanceToSucceed(
            tokenIds,
            dungeon.treasure
        );
        require(chanceToSucceed > 0, "your party has no chance to succeed");

        dungeon.adventuringParty = AdventuringParty({
            owner: msg.sender,
            tokenIds: tokenIds,
            chanceToSucceed: chanceToSucceed
        });

        for (uint256 i = 0; i < tokenIds.length; i++) {
            fantasy.safeTransferFrom(msg.sender, address(this), tokenIds[i]);
        }
        // TODO: Update to vrfv2
        uint256 requestId = COORDINATOR.requestRandomWords(
            keyHash,
            subscriptionId,
            requestConfirmations,
            callbackGasLimit,
            1
        );
        dungeon.requestId = requestId;
        requestIdToDungeon[requestId] = dungeon;

        emit DungeonRaidStarted(dungeonCreator, msg.sender, tokenIds);
    }

    function fulfillRandomWords(uint256 requestId, uint256[] memory randomWords)
        internal
        override
    {
        Dungeon storage dungeon = requestIdToDungeon[requestId];
        // TODO Isnt it said by chainlink that this function must not fail ?
        require(
            dungeon.isBeingRaided(),
            "dungeon does not have a party inside"
        );

        delete dungeon.requestId;

        uint256 roll = (randomWords[0] % 100) + 1;
        if (roll <= dungeon.adventuringParty.chanceToSucceed) {
            // success, transfer ETH to party owner and send back his/her tokens and remove dungeon
            claimableRewards[dungeon.adventuringParty.owner].push(
                DungeonReward({
                    tokenIds: dungeon.adventuringParty.tokenIds,
                    treasure: dungeon.treasure
                })
            );

            emit DungeonRaidOutcome(
                dungeon.creator,
                dungeon.adventuringParty.owner,
                dungeon.adventuringParty.tokenIds,
                roll,
                true
            );
            delete dungeons[dungeon.creator];
            delete requestIdToDungeon[requestId];
        } else {
            claimableRewards[dungeon.creator].push(
                DungeonReward({
                    tokenIds: dungeon.adventuringParty.tokenIds,
                    treasure: 0 // treasure stays in the dungeon
                })
            );

            emit DungeonRaidOutcome(
                dungeon.creator,
                dungeon.adventuringParty.owner,
                dungeon.adventuringParty.tokenIds,
                roll,
                false
            );
            delete dungeon.adventuringParty;
        }
    }

    function withdrawReward(uint256 rewardsIndex) public {
        DungeonReward memory reward = claimableRewards[msg.sender][
            rewardsIndex
        ];
        claimableRewards[msg.sender].remove(rewardsIndex);
        // TODO: Can this be locked by an out of gas ?
        for (uint256 i = 0; i < reward.tokenIds.length; i++) {
            fantasy.safeTransferFrom(
                address(this),
                msg.sender,
                reward.tokenIds[i]
            );
        }
        (bool sent, ) = msg.sender.call{value: reward.treasure}("");
        require(sent, "failed to send eth");
    }

    /// @dev this function can run out gas. Always call it upfront to avoid dungeons being locked by an out of gas.
    function getAventurersChanceToSucceed(
        uint256[] memory tokenIds,
        uint256 treasure
    ) public view returns (uint256) {
        // TODO: Take stats into account ?
        int256 totalLevels = 0;
        for (uint256 i = 0; i < tokenIds.length; i++) {
            // TODO use smaller bounded value for levels to ensure that it cannot have overflow or account for it somehow
            (, , , , uint256 level, ) = fantasy.getCharacterOverview(
                tokenIds[i]
            );
            totalLevels += int256(level);
        }
        // TODO: Test for math operations safety, especially conversions!
        int256 treasureDifficulty = int256(treasure / 1 ether);
        uint256 successChance = uint256(
            (baseSuccessChancePerc - treasureDifficulty + totalLevels)
                .zeroIfNegative()
        );
        return
            successChance <= maxSuccessChancePerc
                ? successChance
                : maxSuccessChancePerc;
    }

    // TODO 0.8: inherit from ERC721Holder instead
    /**
     * @dev See {IERC721Receiver-onERC721Received}.
     *
     * Always returns `IERC721Receiver.onERC721Received.selector`.
     */
    function onERC721Received(
        address,
        address,
        uint256,
        bytes memory
    ) public virtual override returns (bytes4) {
        return this.onERC721Received.selector;
    }
}
