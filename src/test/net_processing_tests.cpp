// Copyright (c) 2025 The Bitcoin Knots developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <chainparams.h>
#include <clientversion.h>
#include <common/args.h>
#include <compat/compat.h>
#include <cstdint>
#include <net.h>
#include <net_processing.h>
#include <netaddress.h>
#include <netbase.h>
#include <netmessagemaker.h>
#include <node/protocol_version.h>
#include <serialize.h>
#include <span.h>
#include <streams.h>
#include <test/util/random.h>
#include <test/util/setup_common.h>
#include <test/util/validation.h>
#include <util/strencodings.h>
#include <util/string.h>
#include <validation.h>

#include <boost/test/unit_test.hpp>

#include <algorithm>
#include <ios>
#include <memory>
//#include <core_memusage.h>
#include <optional>
#include <string>

static Mutex& g_msgproc_mutex = NetEventsInterface::g_msgproc_mutex;

using namespace std::literals;
using namespace util::hex_literals;
using util::ToString;

class PeerManagerImpl;

struct NetProcessingTestFixture : public RegTestingSetup {
    //   void AddToCompactExtraTransactions(PeerManagerImpl* impl, const CTransactionRef& tx) {
    //       LOCK(g_msgproc_mutex);
    //       size_t usage = RecursiveDynamicUsage(*tx);
    //       impl->AddToCompactExtraTransactions(tx, usage);
    //   }

    //   size_t GetMemoryUsage(const PeerManagerImpl* impl) {
    //       LOCK(g_msgproc_mutex);
    //       return impl->blockreconstructionextratxn_memusage;
    //   }
  };


BOOST_FIXTURE_TEST_SUITE(net_processing_tests, NetProcessingTestFixture)

BOOST_FIXTURE_TEST_CASE(blockreconstructionextratxnsize_basic_memory_tracking, NetProcessingTestFixture)
{
    // Test that memory usage is tracked
    // Verify memusage is updated
    // default options (max_extra_txs_size unlimited)
    PeerManager::Options opts;
    auto peerman = PeerManager::make(*m_node.connman, *m_node.addrman, nullptr, *m_node.chainman, *m_node.mempool, *m_node.warnings, opts);
    PeerManagerImpl* impl = static_cast<PeerManagerImpl*>(peerman.get());

    BOOST_CHECK_EQUAL(GetMemoryUsage(impl), 0);

}

