#  Copyright 2024 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Defines the registry for Nearby Connection metrics."""

import immutabledict
from betocq.metrics import metrics_base

MetricDefinition = metrics_base.MetricDefinition
AggregatorType = metrics_base.AggregatorType
NC_METRICS_REGISTRY: immutabledict.immutabledict[str, MetricDefinition] = (
    immutabledict.immutabledict({
        'discoverer_sta_frequency': MetricDefinition(
            AggregatorType.FIRST_VALID, None
        ),
        'advertiser_sta_frequency': MetricDefinition(
            AggregatorType.FIRST_VALID, None
        ),
        'discoverer_max_sta_link_speed_mbps': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'advertiser_max_sta_link_speed_mbps': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'device_source': MetricDefinition(AggregatorType.LAST, None),
        'device_target': MetricDefinition(AggregatorType.LAST, None),
        'target_build_id': MetricDefinition(AggregatorType.LAST, None),
        'target_model': MetricDefinition(AggregatorType.LAST, None),
        'target_gms_version': MetricDefinition(AggregatorType.LAST, None),
        'target_wifi_chipset': MetricDefinition(AggregatorType.LAST, None),
        'wifi_ap_number': MetricDefinition(AggregatorType.LAST, None),
        # Performance latency stats
        'prior_discovery_latency': MetricDefinition(
            AggregatorType.STATS, 'prior_bt_connection_stats'
        ),
        'prior_connection_latency': MetricDefinition(
            AggregatorType.STATS, 'prior_bt_connection_stats'
        ),
        'discovery_latency': MetricDefinition(
            AggregatorType.STATS, 'file_transfer_stats'
        ),
        'connection_latency': MetricDefinition(
            AggregatorType.STATS, 'file_transfer_stats'
        ),
        'upgrade_latency': MetricDefinition(
            AggregatorType.STATS, 'file_transfer_stats'
        ),
        'file_transfer_throughput_kbps': MetricDefinition(
            AggregatorType.STATS, 'file_transfer_stats'
        ),
        'iperf_throughput_kbps': MetricDefinition(
            AggregatorType.STATS, 'file_transfer_stats'
        ),
        # Occurrences counter
        'upgrade_medium': MetricDefinition(
            AggregatorType.COUNTER, 'wifi_upgrade_stats'
        ),
        # Concurrency mode
        'wifi_concurrency_mode': MetricDefinition(
            AggregatorType.FIRST_VALID, 'wifi_concurrency_mode'
        ),
        # Class configurations (Flat, no prefix in Mobly Props)
        'country_code': MetricDefinition(AggregatorType.LAST, 'test_config'),
        'advertising_discovery_medium': MetricDefinition(
            AggregatorType.LAST, 'test_config'
        ),
        'connection_medium': MetricDefinition(
            AggregatorType.LAST, 'test_config'
        ),
        'upgrade_medium_under_test': MetricDefinition(
            AggregatorType.LAST, 'test_config'
        ),
        'is_dbs_mode': MetricDefinition(AggregatorType.LAST, 'test_config'),
        'is_2g_only': MetricDefinition(AggregatorType.LAST, 'test_config'),
        'is_mcc_mode': MetricDefinition(AggregatorType.LAST, 'test_config'),
        'discoverer_wifi_ssid': MetricDefinition(
            AggregatorType.LAST, 'test_config'
        ),
        'advertiser_wifi_ssid': MetricDefinition(
            AggregatorType.LAST, 'test_config'
        ),
        'iperf_to_d2d_throughput_ratio': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'is_discoverer_network_owner': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'wlan_throughput_cap_mbps': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'all_tests_should_be_skipped': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'd2d_type': MetricDefinition(AggregatorType.EXCLUDE_AGGREGATING, None),
        'medium_frequency': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'active_nc_fail_reason': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'result_message': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'discoverer_sta_latency': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'advertiser_sta_latency': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'prior_nc_fail_reason': MetricDefinition(
            AggregatorType.EXCLUDE_AGGREGATING, None
        ),
        'speed_target': MetricDefinition(
            AggregatorType.FIRST_VALID, 'file_transfer_stats'
        ),
    })
)
