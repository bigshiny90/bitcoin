#!/usr/bin/env python3
# Copyright (c) 2025 The Bitcoin Knots developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test blockreconstructionextratxnsize option with compact blocks."""

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
    OP_RETURN,
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
        ]]
        self.utxos = []

    def build_block_on_tip(self, node):
        """Build a block on top of the current tip."""
        block = create_block(tmpl=node.getblocktemplate(NORMAL_GBT_REQUEST_PARAMS))
        block.solve()
        return block

    def make_utxos(self):
        """Generate blocks to create UTXOs for the wallet."""
        self.generate(self.wallet, COINBASE_MATURITY + 250)

    def restart_node_with_limit(self, limit_mbytes):
        """Restart node with specific blockreconstructionextratxnsize limit."""
        self.log.info(f"Restarting node with limit: {limit_mbytes} MB")
        self.restart_node(0, extra_args=[
            "-acceptnonstdtxn=1",
            f"-blockreconstructionextratxnsize={limit_mbytes}"
        ])
        # Reconnect test peer after restart
        self.segwit_node = self.nodes[0].add_p2p_connection(TestP2PConn())
        self.segwit_node.send_and_ping(msg_sendcmpct(announce=True, version=2))

    def create_extra_pool_transactions(self, num_txs, large_tx=False):
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
        node = self.nodes[0]

        original_txs, replacement_txs = self.create_extra_pool_transactions(num_txs, large_tx)

        for i, original in enumerate(original_txs):
            tx_obj = tx_from_hex(original['hex'])
            self.segwit_node.send_and_ping(msg_tx(tx_obj))

        for i, replacement in enumerate(replacement_txs):
            tx_obj = tx_from_hex(replacement['hex'])
            self.segwit_node.send_and_ping(msg_tx(tx_obj))

        return original_txs, replacement_txs

    def send_compact_block(self, transactions, indices):
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

        return {
            "block": block,
            "getblocktxn": getblocktxn,
            "num_tx_requested": num_tx_requested
        }

    def test_unlimited_default(self):
        """Test that default (unlimited) memory allows full reconstruction."""
        self.log.info("Testing default unlimited memory...")

        # test logic:
        # create 100 transaction pairs (original + replacement RBF versions)
        # 100 is max tx limit for compact blocks
        # Use large transactions (~50KB each-ish)
        # create/send compact block with all 100 original transactions (which should still be in extra pool)
        # no memory limit means all transactions should be reconstructed successfully

        self.log.info("Creating 100 large transactions (~20KB each) for unlimited memory test")
        original_txs, replacement_txs = self.populate_extra_pool(100, large_tx=True)
        result = self.send_compact_block(original_txs, list(range(100)))

        # Verify reconstruction
        # Node should not request any transactions (because all are in mempool or extra pool)
        assert result["getblocktxn"] is None, "Node shouldn't request transactions with unlimited memory"
        # block should have been rejected, as they are double spends
        assert_equal(int(self.nodes[0].getbestblockhash(), 16), result["block"].hashPrevBlock)

    def test_zero_limit(self):
        """Test that zero limit prevents any reconstruction."""
        self.log.info("Testing 0 memory limit...")
        self.restart_node_with_limit(0)

        original_txs, replacement_txs = self.populate_extra_pool(1)
        result = self.send_compact_block(original_txs, [0])

        # Should fail - no memory for extra pool
        assert result["getblocktxn"] is not None, "Node should try to request when zero memory"
        assert_equal(int(self.nodes[0].getbestblockhash(), 16), result["block"].hashPrevBlock)

    def test_small_limit_eviction(self):
        """Test that small limit causes transaction eviction."""
        self.log.info("Testing small memory limit eviction...")

        limit_mb = 0.015 # MB
        self.restart_node_with_limit(limit_mb)

        original_txs, replacement_txs = self.populate_extra_pool(50)

        # Test all transactions to determine evictions
        in_pool = []
        evicted = []

        for i in range(50):
            result = self.send_compact_block(original_txs, [i])

            if result["getblocktxn"]:
                evicted.append(i)
            else:
                in_pool.append(i)

            assert_equal(int(self.nodes[0].getbestblockhash(), 16), result["block"].hashPrevBlock)

        # Verify evictions happened
        assert len(evicted) > 0, "No transactions were evicted"
        assert len(in_pool) > 0, "All transactions were evicted"

        # Verify specific txs
        assert 0 in evicted, "Transaction 0 should be evicted"
        assert 49 in in_pool, "Transaction 49 should remain in pool"

    def test_exact_limit_boundary(self):
        """Test behavior at exact memory limit boundary."""
        self.log.info("Testing exact memory limit boundary...")

        limit_mb = 0.015
        self.restart_node_with_limit(limit_mb)

        tx_count = 36
        self.log.info(f"Total tx count: {tx_count}")
        original_txs, _ = self.populate_extra_pool(tx_count)

        evicted_1 = []
        in_pool_1 = []

        for i in range(tx_count):
            result = self.send_compact_block(original_txs, [i])
            if result["getblocktxn"]:
              evicted_1.append(i)
            else:
              in_pool_1.append(i)

        pool_capacity = len(in_pool_1)  # How many the pool can hold
        evicted_cnt = len(evicted_1)
        self.log.info(f"Pool capacity: {pool_capacity} transactions")
        self.log.info(f"Evicted: {evicted_cnt} transactions")
        assert pool_capacity == tx_count, f"Expected pool capacity of {tx_count}, got {pool_capacity}"
        assert evicted_cnt == 0, f"Expected no evictions, got {evicted_cnt}"

        # add one more
        new_tx_count = 1
        self.log.info(f"Adding {new_tx_count} new transactions to pool")
        new_txs, _ = self.populate_extra_pool(new_tx_count)
        evicted_2 = []

        # # check originals again
        cutoff2 = None
        for i in range(tx_count):
            result = self.send_compact_block(original_txs, [i])
            if result["getblocktxn"]:
              evicted_2.append(i)

        evicted = len(evicted_2)
        self.log.info(f"Evicted count: {evicted}, Expected: {new_tx_count}")
        assert evicted == new_tx_count, f"Should evict exactly {new_tx_count}: actual {evicted}"

        for i in range(new_tx_count):
            result = self.send_compact_block(new_txs, [i])
            assert result["getblocktxn"] is None, f"New transaction {i} should be in pool"


    def test_single_transaction_exceeds_limit(self):
        """Test that a single transaction larger than the entire memory limit is rejected."""
        self.log.info("Testing single transaction exceeding memory limit...")

        # Set very small memory limit (1KB)
        limit_mb = 0.001  # 1KB
        self.restart_node_with_limit(limit_mb)

        # Create one large transaction (~20KB) that exceeds the entire limit
        self.log.info(f"Creating large transaction (~20KB) with memory limit of {limit_mb}MB")
        original_txs, replacement_txs = self.populate_extra_pool(1, large_tx=True)

        result = self.send_compact_block(original_txs, [0])

        assert result["getblocktxn"] is not None, "Node should request transaction"
        assert_equal(result["num_tx_requested"], 1)
        assert_equal(int(self.nodes[0].getbestblockhash(), 16), result["block"].hashPrevBlock)

    def run_test(self):
        self.wallet = MiniWallet(self.nodes[0])

        # Setup the p2p connection
        self.segwit_node = self.nodes[0].add_p2p_connection(TestP2PConn())

        # Create UTXOs for testing
        self.make_utxos()

        # Ensure segwit is active
        assert softfork_active(self.nodes[0], "segwit")

        # Run individual tests
        self.test_unlimited_default()
        self.test_zero_limit()
        self.test_small_limit_eviction()
        self.test_exact_limit_boundary()
        self.test_single_transaction_exceeds_limit()


if __name__ == '__main__':
    CompactBlocksBlockReconstructionLimitTest(__file__).main()
