## Overview

Randomly geenrated fantasy characters. 
Addresses can create a dungeon with treasure by staking their ETH.
Players can the send their characters to the dungeon.
If they win, they claim the ETH and the dungeon is destroyed. 
If they loose, they get captured and get their ownership transferred to the dungeon creator.

Character races can be added after the contract is on chain.


## Code overview:

Fantasy.sol has the core NFT logic with the character generation.
DungeonManager.sol handles the dungoen creation / raiding logic.

In modules, you can find race modules as well as the base race module to inherit from if you want to create your own.

## TODOs:

Character class module ?

1. Finish Todos in DungeonManager.sol
2. Test raiding a dungeon that does not exist: should not work
3. approve only the tokens raiding the dungeon ? Setting approval for all is scary
4. withdraw artist fee instead of making people pay for transfer gas
5. What if token transfer fails, can a DOS attack be done ?
6. Remove levels and use stats for dungeon (leveling up can be built as aseperate funcionnality later)
7. Finish unit tests
8. Make sure math is safe
9.  Use Address lib from open zeppelin for eth transfer
10. Check Open Zeppelin docs for anything that we can reuse
11. Fuzzy testing
12. CI/CD before deployment that runs all tests
13. Cleanup code
14. Allow people to change race modules based on votes (DAO). built in solution from open zeppelin for DAO race module changes ?
15.  Picture generation (basic). Image parts hosted on IPFS and assembling done in smart contract, but picture generation done by third party for convenience should be ok. Any way to make also decentralized, with for ex chainlink ?
16. More unit tests ?
17. Somethign to automatically refill the subscription ? Is there a generic solution for this ?
My idea is a system that automtically uses the eth fees or a possible own customt token to pay for the LINK, that way that is abstracted away from users
and the system can be made to always be able to provide the necessary LINk. For example, adjusting the fee cost based on LINK price. This system could be its
own project that can be used by other projects...