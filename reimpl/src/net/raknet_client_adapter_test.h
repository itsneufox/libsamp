#ifndef SAMPDLL_NET_RAKNET_CLIENT_ADAPTER_TEST_H
#define SAMPDLL_NET_RAKNET_CLIENT_ADAPTER_TEST_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Internal host-test seam. This accepts the same complete packet buffer as
 * RakClientInterface::Receive(), including an optional ID_TIMESTAMP prefix.
 * It is intentionally kept outside the public include tree.
 */
int samp_raknet_test_ingest_remote_edge_sync(const unsigned char *data,
                                             unsigned int bytes);

/*
 * Internal test seam for the production drain guard. Returns non-zero once a
 * single drain has filled the shared movement snapshot ring.
 */
int samp_raknet_test_remote_movement_drain_should_yield(
    unsigned int sequence_before_drain, unsigned int current_sequence);

#ifdef __cplusplus
}
#endif

#endif
