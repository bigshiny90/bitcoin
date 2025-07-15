#!/usr/bin/env python3
# Copyright (c) 2025 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test blockreconstructionextratxn and blockreconstructionextratxnsize options with compact blocks."""

import random

from test_framework.blocktools import (
    COINBASE_MATURITY,
    NORMAL_GBT_REQUEST_PARAMS,
    create_block,
)
from test_framework.messages import (
    CTxOut,
    HeaderAndShortIDs,
    MAX_BIP125_RBF_SEQUENCE,
    MSG_BLOCK,
    msg_cmpctblock,
    msg_sendcmpct,
    msg_tx,
    tx_from_hex,
)
from test_framework.p2p import (
    P2PInterface,
    p2p_lock,
)
from test_framework.script import (
    CScript,
    OP_DROP,
    OP_TRUE,
)
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal,
    softfork_active,
)
from decimal import Decimal
from test_framework.wallet import MiniWallet


# TestP2PConn: A peer we use to send messages to bitcoind, and store responses.
class TestP2PConn(P2PInterface):
    def __init__(self):
        super().__init__()
        self.last_sendcmpct = []
        self.block_announced = False
        # Store the hashes of blocks we've seen announced.
        # This is for synchronizing the p2p message traffic,
        # so we can eg wait until a particular block is announced.
        self.announced_blockhashes = set()

    def on_sendcmpct(self, message):
        self.last_sendcmpct.append(message)

    def on_cmpctblock(self, message):
        self.block_announced = True
        self.last_message["cmpctblock"].header_and_shortids.header.calc_sha256()
        self.announced_blockhashes.add(self.last_message["cmpctblock"].header_and_shortids.header.sha256)

    def on_headers(self, message):
        self.block_announced = True
        for x in self.last_message["headers"].headers:
            x.calc_sha256()
            self.announced_blockhashes.add(x.sha256)

    def on_inv(self, message):
        for x in self.last_message["inv"].inv:
            if x.type == MSG_BLOCK:
                self.block_announced = True
                self.announced_blockhashes.add(x.hash)

    # Requires caller to hold p2p_lock
    def received_block_announcement(self):
        return self.block_announced

    def clear_block_announcement(self):
        with p2p_lock:
            self.block_announced = False
            self.last_message.pop("inv", None)
            self.last_message.pop("headers", None)
            self.last_message.pop("cmpctblock", None)

    def clear_getblocktxn(self):
        with p2p_lock:
            self.last_message.pop("getblocktxn", None)


class CompactBlocksBlockReconstructionLimitTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 1
        self.extra_args = [[
            "-acceptnonstdtxn=1",
            "-debug=net",
        ]]
        self.utxos = []

    def build_block_on_tip(self, node):
        """Build a block on top of the current tip."""
        block = create_block(tmpl=node.getblocktemplate(NORMAL_GBT_REQUEST_PARAMS))
        block.solve()
        return block

    def make_utxos(self):
        """Generate blocks to create UTXOs for the wallet."""
        self.generate(self.wallet, COINBASE_MATURITY + 400)

    def restart_node_with_limit(self, memory_mb=None, count=None):
        """Restart node with specific memory and/or count limits."""
        extra_args = ["-acceptnonstdtxn=1", "-debug=net"]

        if memory_mb is not None:
            self.log.info(f"Setting memory limit: {memory_mb} MB")
            extra_args.append(f"-blockreconstructionextratxnsize={memory_mb}")

        if count is not None:
            self.log.info(f"Setting transaction count limit: {count}")
            extra_args.append(f"-blockreconstructionextratxn={count}")

        self.log.info(f"Restarting node with args: {extra_args}")
        self.restart_node(0, extra_args=extra_args)
        self.segwit_node = self.nodes[0].add_p2p_connection(TestP2PConn())
        self.segwit_node.send_and_ping(msg_sendcmpct(announce=True, version=2))

    def create_extra_pool_transactions(self, num_txs, large_tx=False):
        """Create pairs of original and replacement RBF transactions."""
        original_txs = []
        replacement_txs = []

        for i in range(num_txs):
            utxo = self.wallet.get_utxo()

            if large_tx:
                # Create larger transactions by adding many outputs
                # Target ~20KB per transaction

                # from: rbf_extra_pool_explanation.md
                # Create original transaction with low fee and extra outputs
                original = self.wallet.create_self_transfer(
                    utxo_to_spend=utxo,
                    sequence=MAX_BIP125_RBF_SEQUENCE,  # 0xfffffffd - RBF enabled
                    fee_rate=Decimal('0.001')
                )
                original_tx = tx_from_hex(original['hex'])

                num_outputs = 100
                for j in range(num_outputs):
                    padding_data = b'x' * 190
                    script = CScript([padding_data, OP_DROP, OP_TRUE])
                    original_tx.vout.append(CTxOut(100, script))

                original_tx.rehash()
                original['hex'] = original_tx.serialize().hex()
                original['txid'] = original_tx.hash
                original['wtxid'] = original_tx.getwtxid()
                original_txs.append(original)

                # Create rbf transaction, higher fee with same outputs
                replacement = self.wallet.create_self_transfer(
                    utxo_to_spend=utxo,
                    sequence=MAX_BIP125_RBF_SEQUENCE - 1,  # Still RBF enabled
                    fee_rate=Decimal('0.01')
                )
                replacement_tx = tx_from_hex(replacement['hex'])

                # Add same outputs to replacement
                for j in range(100):
                    padding_data = b'x' * 190
                    script = CScript([padding_data, OP_DROP, OP_TRUE])
                    replacement_tx.vout.append(CTxOut(100, script))

                replacement_tx.rehash()
                replacement['hex'] = replacement_tx.serialize().hex()
                replacement['txid'] = replacement_tx.hash
                replacement['wtxid'] = replacement_tx.getwtxid()
                replacement_txs.append(replacement)
            else:
                # Create normal sized transactions
                # from: rbf_extra_pool_explanation.md
                # Create original transaction with low fee
                original = self.wallet.create_self_transfer(
                    utxo_to_spend=utxo,
                    sequence=MAX_BIP125_RBF_SEQUENCE,  # 0xfffffffd - RBF enabled
                    fee_rate=Decimal('0.001')
                )
                original_txs.append(original)

                # Create rbf transaction, higher fee
                replacement = self.wallet.create_self_transfer(
                    utxo_to_spend=utxo,
                    sequence=MAX_BIP125_RBF_SEQUENCE - 1,  # Still RBF enabled
                    fee_rate=Decimal('0.01')
                )
                replacement_txs.append(replacement)

        return original_txs, replacement_txs

    def populate_extra_pool(self, num_txs, large_tx=False):
        """Populate the extra transaction pool by sending RBF transaction pairs."""
        node = self.nodes[0]

        original_txs, replacement_txs = self.create_extra_pool_transactions(num_txs, large_tx)

        for i, original in enumerate(original_txs):
            tx_obj = tx_from_hex(original['hex'])
            self.segwit_node.send_message(msg_tx(tx_obj))  # Don't wait

        for i, replacement in enumerate(replacement_txs):
            tx_obj = tx_from_hex(replacement['hex'])
            self.segwit_node.send_message(msg_tx(tx_obj))  # Don't wait

        # Single sync at the end for all transactions
        self.segwit_node.sync_with_ping()

        return original_txs, replacement_txs

    def send_compact_block(self, transactions, indices):
        """Send a compact block and check which transactions are requested for reconstruction."""
        node = self.nodes[0]

        # Create block with specified transactions
        block = self.build_block_on_tip(node)

        for i in indices:
            tx_obj = tx_from_hex(transactions[i]['hex'])
            block.vtx.append(tx_obj)
        block.hashMerkleRoot = block.calc_merkle_root()
        block.solve()

        # Send as compact block
        cmpct_block = HeaderAndShortIDs()
        cmpct_block.initialize_from_block(block, use_witness=True)
        self.segwit_node.send_and_ping(msg_cmpctblock(cmpct_block.to_p2p()))

        # Check if node requested missing transactions
        with p2p_lock:
            getblocktxn = self.segwit_node.last_message.get("getblocktxn")

        num_tx_requested = len(getblocktxn.block_txn_request.indexes) if getblocktxn else 0
        self.segwit_node.clear_getblocktxn()

        # Convert differential encoding to absolute indices (from BlockTransactionRequest)
        missing_indices = []
        if getblocktxn:
            absolute_block_indices = getblocktxn.block_txn_request.to_absolute()
            # Convert from block positions to transaction indices (subtract 1 for coinbase)
            missing_indices = [idx - 1 for idx in absolute_block_indices]

        return {
            "block": block,
            "getblocktxn": getblocktxn,
            "num_tx_requested": num_tx_requested,
            "missing_indices": missing_indices
        }


    # TEST: blockreconstructionextratxn

    def test_extratxnpool_disabled(self):
        """Test that setting count to 0 disables the extra transaction pool."""
        self.log.info("Testing disabled extra transaction pool (0 capacity)...")

        self.restart_node_with_limit(count=0)
        buffersize = 5
        original_txs, _ = self.populate_extra_pool(buffersize)

        indices = list(range(buffersize))
        result = self.send_compact_block(original_txs, indices)
        assert result["missing_indices"] == indices, f"All transactions should be requested with disabled extra txn pool, but only {result['missing_indices']} are missing"
        self.log.info(f"✓ All {buffersize} transactions are missing (extra txn pool disabled)")

    def test_extratxnpool_capacity(self):
        """Test extra transaction pool holds exactly 50 transactions."""
        self.log.info("Testing extra transaction pool capacity (50 transactions)...")

        buffersize = 50  # size
        self.restart_node_with_limit(count=buffersize)

        original_txs, _ = self.populate_extra_pool(buffersize)

        indices = list(range(buffersize))
        result = self.send_compact_block(original_txs, indices)

        assert result["missing_indices"] == [], f"Expected all original transactions to be in extra txn pool, but {result['missing_indices']} are missing"
        self.log.info("✓ All original transactions are in the extra txn pool")

        # Test that adding a 51st transaction causes eviction
        self.log.info("Adding 51st transaction to test eviction...")
        new_txs, _ = self.populate_extra_pool(1)

        # Check original transactions again - first one should be evicted
        result2 = self.send_compact_block(original_txs, indices)
        assert result2["missing_indices"] == [0], f"Expected transaction 0 to be evicted, but got {result2['missing_indices']}"
        self.log.info("✓ Transaction 0 was evicted as expected")

    def test_single_extratxnpool_capacity(self):
        """Test edge case of single capacity extra transaction pool."""
        self.log.info("Testing single capacity extra transaction pool...")

        self.restart_node_with_limit(count=1)
        tx_count = 5  # number of transactions to test

        original_txs, _ = self.populate_extra_pool(tx_count)

        indices = list(range(tx_count))
        result = self.send_compact_block(original_txs, indices)

        expected_missing = list(range(4))
        assert result["missing_indices"] == expected_missing, f"Expected transactions 0-3 to be evicted, but got {result['missing_indices']}"

    def test_extratxn_buffer_wraparound(self):
        """Test that adding transactions to a full buffer evicts oldest slots."""
        self.log.info("Testing extratxn buffer wraparound - fill buffer then add more...")

        buffersize = 20  # buffer size, total txns size

        # number of new transactions to add
        # over MAX_BLOCKS_IN_TRANSIT_PER_PEER (16)?
        new_tx_count = 17
        self.restart_node_with_limit(count=buffersize)

        # Step 1: Fill the buffer with tx pairs (original + replacement)
        original_txs, _ = self.populate_extra_pool(buffersize)

        # Verify all original transactions are in the extra pool
        indices = list(range(buffersize))
        result = self.send_compact_block(original_txs, indices)
        assert result["missing_indices"] == [], f"Expected all original transactions to be in extra pool, but {result['missing_indices']} are missing"
        self.log.info("✓ All original transactions are in the extra pool")

        # Step 2: Add more transaction pairs
        self.log.info(f"Step 2: Adding {new_tx_count} more transaction pairs (should wrap and evict slots 0-{new_tx_count-1})")
        new_txs, _ = self.populate_extra_pool(new_tx_count)

        result2 = self.send_compact_block(original_txs, indices)

        # Verify wraparound worked correctly - first new_tx_count should be evicted
        expected_missing = list(range(new_tx_count))  # First 16 should be evicted
        assert result2['missing_indices'] == expected_missing, f"Expected indices {expected_missing} to be evicted, but got {result2['missing_indices']}"
        self.log.info(f"✓ Wraparound worked correctly! Transactions {expected_missing} were evicted as expected")


     # TEST: blockreconstructionextratxnsize

    def test_extratxn_zero_memorylimit(self):
        """Test extra transaction pool zero memory limit prevents extra txn pool."""
        self.log.info("Testing extra transaction pool zero memory limit prevents extra txn pool...")
        self.restart_node_with_limit(memory_mb=0)

        original_txs, replacement_txs = self.populate_extra_pool(1)
        result = self.send_compact_block(original_txs, [0])

        # Should fail - no memory for extra pool
        assert result["getblocktxn"] is not None, "Node should try to request when zero memory"
        assert_equal(int(self.nodes[0].getbestblockhash(), 16), result["block"].hashPrevBlock)

    def test_extratxn_memorylimit_eviction(self):
        """Test extra transaction pool memory limit eviction behavior."""
        self.log.info("Testing extra transaction pool memory limit eviction behavior...")

        buffersize = 60  # Need enough large transactions to exceed 1MB

        # First, test with 1MB limit - should fail
        self.log.info(f"Step 1: Testing with 1MB limit for {buffersize} large transactions")
        self.restart_node_with_limit(memory_mb=1, count=buffersize)

        # Create 60 large transactions (~20KB each = ~1.2MB total)
        # This exceeds the 1MB limit
        self.log.info(f"Creating {buffersize} large transactions (~20KB each, ~1.2MB total)")
        original_txs, _ = self.populate_extra_pool(buffersize, large_tx=True)

        indices = list(range(buffersize))
        result_small = self.send_compact_block(original_txs, indices)

        # Should have evictions - can't fit 1.2MB in 1MB limit
        assert len(result_small["missing_indices"]) > 0, "1MB limit should cause evictions for 1.2MB of transactions"
        evicted_count = len(result_small["missing_indices"])
        self.log.info(f"✓ 1MB limit caused {evicted_count} evictions (can't fit ~1.2MB of transactions)")

        # Now test with larger memory limit to show it succeeds
        self.log.info(f"Step 2: Testing with 2MB limit for same {buffersize} large transactions")
        self.restart_node_with_limit(memory_mb=2, count=buffersize)

        original_txs, _ = self.populate_extra_pool(buffersize, large_tx=True)

        result_large = self.send_compact_block(original_txs, indices)

        # Should have NO evictions with 2MB limit
        assert result_large["missing_indices"] == [], f"2MB limit should store all transactions"
        self.log.info(f"✓ 2MB limit successfully stores all {buffersize} large transactions (~1.2MB)")

    def test_extratxn_memorylimit_boundary(self):
        """Test extra transaction pool at exact memory limit boundary."""
        self.log.info("Testing extra transaction pool exact memory limit boundary...")

        limit_mb = 1  # Minimum allowed
        self.restart_node_with_limit(memory_mb=limit_mb)

        test_count = 100
        original_txs, _ = self.populate_extra_pool(test_count, large_tx=True)

        indices = list(range(test_count))
        result = self.send_compact_block(original_txs, indices)

         # Find the boundary - how many fit vs how many were evicted
        num_evicted = len(result["missing_indices"])
        num_fit = test_count - num_evicted

        # Now restart and add exactly the number that fit
        self.restart_node_with_limit(memory_mb=limit_mb)
        original_txs, _ = self.populate_extra_pool(num_fit, large_tx=True)

        # Verify all fit
        indices = list(range(num_fit))
        result = self.send_compact_block(original_txs, indices)
        assert result["missing_indices"] == [], f"Expected all {num_fit} transactions to fit at boundary"

        # Add one more transaction - should evict exactly one
        self.log.info("Adding one more transaction at the boundary...")
        new_txs, _ = self.populate_extra_pool(1, large_tx=True)

        # Check original transactions again
        result2 = self.send_compact_block(original_txs, indices)
        assert len(result2["missing_indices"]) == 1, f"Expected exactly 1 eviction at boundary"
        assert result2["missing_indices"] == [0], f"Expected oldest transaction (0) to be evicted"

        self.log.info("Memory limit boundary behavior verified - one transaction evicted when limit exceeded")


    def run_test(self):
        self.wallet = MiniWallet(self.nodes[0])

        # Setup the p2p connection
        self.segwit_node = self.nodes[0].add_p2p_connection(TestP2PConn())

        # Create UTXOs for testing
        self.make_utxos()

        # Ensure segwit is active
        assert softfork_active(self.nodes[0], "segwit")

        # Extra Txn capacity tests
        self.test_extratxnpool_disabled()
        self.test_extratxnpool_capacity()
        self.test_single_extratxnpool_capacity()

        # Extra Txn wraparound tests
        self.test_extratxn_buffer_wraparound()

        # Memory limit tests
        self.test_extratxn_zero_memorylimit()
        self.test_extratxn_memorylimit_eviction()
        self.test_extratxn_memorylimit_boundary()


if __name__ == '__main__':
    CompactBlocksBlockReconstructionLimitTest(__file__).main()
