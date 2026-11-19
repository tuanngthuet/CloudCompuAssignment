"""Offline tests: fake AWS responses only; never connect to AWS."""
import csv
import json
from pathlib import Path
import unittest
from types import SimpleNamespace

import chart
import collect

TEST_ROOT = Path(__file__).resolve().parents[3] / ".local" / "c1-test"
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class FakeAWS:
    def __init__(self):
        self.calls = []
        self.errors = []
        self.asg_activity_status = "InProgress"

    def call(self, service, operation, *options, input_data=None):
        self.calls.append((service, operation, options))
        if operation == "get-caller-identity":
            return {"Account": "123456789012"}
        if operation == "describe-db-instances":
            return {"DBInstances": [{"DBInstanceStatus": "available", "MultiAZ": True,
                                     "BackupRetentionPeriod": 1}]}
        if operation == "describe-account-attributes":
            return {"AccountQuotas": [{"AccountQuotaName": "DBInstances", "Max": 20, "Used": 1}]}
        if operation == "describe-capacity-providers":
            return {"capacityProviders": [{"name": "labseat-lab", "status": "ACTIVE",
                     "autoScalingGroupProvider": {"autoScalingGroupArn": "arn:aws:autoscaling:::autoScalingGroup:asg",
                                                  "managedScaling": {"status": "ENABLED"}}}]}
        if operation == "describe-services":
            return {"services": [{"serviceName": "api", "desiredCount": 2, "runningCount": 2,
                                  "pendingCount": 0, "deployments": [{"rolloutState": "COMPLETED"}]},
                                 {"serviceName": "worker", "desiredCount": 1, "runningCount": 1,
                                  "pendingCount": 0}, {"serviceName": "publisher", "desiredCount": 1,
                                                       "runningCount": 1, "pendingCount": 0}]}
        if operation == "describe-target-health":
            return {"TargetHealthDescriptions": [{"TargetHealth": {"State": "healthy"}},
                                                  {"TargetHealth": {"State": "healthy"}}]}
        if operation == "describe-auto-scaling-groups":
            return {"AutoScalingGroups": [{"MinSize": 2, "MaxSize": 6, "DesiredCapacity": 3,
                    "Instances": [{"LifecycleState": "InService", "HealthStatus": "Healthy",
                                   "InstanceId": "i-456"}] * 3}]}
        if operation == "describe-scaling-activities":
            if service == "autoscaling":
                return {"Activities": [{"ActivityId": "asg-1", "StatusCode": self.asg_activity_status,
                         "StartTime": "2026-11-19T00:00:00Z", "Description": "Launching EC2 instance"}]}
            return {"ScalingActivities": [{"ActivityId": "ecs-1", "StatusCode": "Successful",
                     "StartTime": "2026-11-19T00:00:00Z", "Description": "API desired 2 to 3"}]}
        if operation == "describe-alarms":
            return {"MetricAlarms": []}
        if operation == "list-container-instances":
            return {"containerInstanceArns": ["ci-1", "ci-2"]}
        if operation == "describe-container-instances":
            return {"containerInstances": [{"attributes": [{"name": "ecs.availability-zone",
                    "value": "ap-southeast-2a"}], "runningTasksCount": 1,
                    "remainingResources": [{"name": "MEMORY", "integerValue": 900},
                    {"name": "ENI", "integerValue": 1}]}, {"attributes": [{"name": "ecs.availability-zone",
                    "value": "ap-southeast-2b"}], "runningTasksCount": 2,
                    "remainingResources": [{"name": "MEMORY", "integerValue": 400},
                    {"name": "ENI", "integerValue": 0}]}]}
        if operation == "get-metric-data":
            request = json.loads(Path(input_data).read_text(encoding="utf-8"))
            self.queries = request["MetricDataQueries"]
            results = [{"Id": "m0", "Values": [42.0],
                        "Timestamps": ["2026-11-19T00:00:00Z"]}]
            results += [{"Id": q["Id"], "Values": [120.0],
                         "Timestamps": ["2026-11-19T00:00:00Z"]}
                        for q in self.queries
                        if q["MetricStat"]["Metric"]["MetricName"] == "RequestCount"]
            return {"MetricDataResults": results}
        return {}


def args():
    return SimpleNamespace(expected_account="123456789012", region="ap-southeast-2",
        cluster="labseat-lab", api_service="api", worker_service="worker",
        publisher_service="publisher", asg="asg", target_group="arn:target",
        target_group_suffix="targetgroup/lab/1", alb_suffix="app/lab/1",
        capacity_provider="labseat-lab", db="db", cache_cluster="cache-1",
        cache_cluster_replica="cache-2",
        queue="queue", dlq="dlq", alarm_prefix="labseat-", db_budget=66,
        instance_ids=["i-123"], queue_url="", dlq_url="", sns_topic="")


class OfflineTest(unittest.TestCase):
    def test_scaling_activity_dedup_and_status_transition(self):
        fake, seen = FakeAWS(), set()
        first = collect.scaling_activities(fake, args(), "2026-11-19T00:00:30Z", seen)
        self.assertEqual({row["source"] for row in first}, {"asg", "ecs"})
        self.assertEqual(collect.scaling_activities(fake, args(), "2026-11-19T00:01:00Z", seen), [])
        fake.asg_activity_status = "Successful"
        changed = collect.scaling_activities(fake, args(), "2026-11-19T00:01:30Z", seen)
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["status"], "Successful")

    def test_identity_mismatch_stops_before_resource_calls(self):
        fake, options = FakeAWS(), args()
        options.expected_account = "000000000000"
        with self.assertRaises(RuntimeError):
            collect.preflight(fake, options, TEST_ROOT)
        self.assertEqual([c[1] for c in fake.calls], ["get-caller-identity"])

    def test_snapshot_and_metric_dimensions_and_missing(self):
        fake, options = FakeAWS(), args()
        report = collect.preflight(fake, options, TEST_ROOT)
        self.assertEqual(report["checks"]["healthy_targets"], 2)
        self.assertEqual(report["checks"]["capacity_provider"][0]["managed_scaling"], "ENABLED")
        self.assertEqual(report["checks"]["redis_metric_nodes"]["node_2"], "cache-2")
        rows = []
        _, group, _ = collect.describe(fake, options, rows, "2026-11-19T00:00:00Z")
        collect.cloudwatch(fake, options, rows, "2026-11-19T00:00:00Z", TEST_ROOT,
                           [i["InstanceId"] for i in group["Instances"]])
        by_name = {r["metric"]: r for r in rows}
        self.assertEqual(by_name["asg.in_service"]["value"], 3)
        self.assertEqual(by_name["ecs.az_a.eni_remaining"]["value"], 1)
        self.assertEqual(by_name["ecs.az_b.eni_remaining"]["value"], 0)
        self.assertEqual(by_name["ecs.az_a.running_tasks"]["value"], 1)
        self.assertEqual(by_name["ecs.az_b.running_tasks"]["value"], 2)
        self.assertEqual(by_name["ecs.cpu_percent"]["value"], 42.0)
        self.assertEqual(by_name["alb.request_count"]["value"], 120.0)
        self.assertEqual(by_name["alb.rps"]["value"], 2.0)
        self.assertEqual(by_name["rds.connections"]["status"], "MISSING_OR_DELAYED")
        self.assertEqual(by_name["alb.target_4xx"]["status"], "MISSING_OR_DELAYED")
        credits = [q["MetricStat"]["Metric"]["Dimensions"] for q in fake.queries
                   if q["MetricStat"]["Metric"]["MetricName"] == "CPUCreditBalance"]
        self.assertIn([{"Name": "InstanceId", "Value": "i-123"}], credits)
        self.assertIn([{"Name": "InstanceId", "Value": "i-456"}], credits)
        cache_dimensions = {q["MetricStat"]["Metric"]["Dimensions"][0]["Value"]
                            for q in fake.queries
                            if q["MetricStat"]["Metric"]["MetricName"] == "CurrConnections"}
        self.assertEqual(cache_dimensions, {"cache-1", "cache-2"})

    def test_missing_container_task_count_is_not_zero(self):
        class MissingCountAWS(FakeAWS):
            def call(self, service, operation, *options, input_data=None):
                result = super().call(service, operation, *options, input_data=input_data)
                if operation == "describe-container-instances":
                    result["containerInstances"][1].pop("runningTasksCount")
                return result

        rows = []
        collect.describe(MissingCountAWS(), args(), rows, "2026-11-19T00:00:00Z")
        by_name = {r["metric"]: r for r in rows}
        self.assertEqual(by_name["ecs.az_b.running_tasks"]["status"], "MISSING")
        self.assertEqual(by_name["ecs.az_b.running_tasks"]["value"], "")

    def test_chart_from_synthetic_csv(self):
        path = TEST_ROOT / "metrics.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=collect.FIELDS)
            writer.writeheader()
            for i, value in enumerate((2, 3, 4)):
                writer.writerow({"sample_at": f"2026-11-19T00:0{i}:00Z", "metric": "asg.desired",
                                 "value": value, "unit": "Count", "source_at": "2026-11-19T00:00:00Z",
                                 "status": "OBSERVED"})
                for metric, observed in (("ecs.api.running", 2), ("alb.healthy_targets", 2)):
                    writer.writerow({"sample_at": f"2026-11-19T00:0{i}:00Z", "metric": metric,
                                     "value": observed, "unit": "Count", "source_at": "2026-11-19T00:00:00Z",
                                     "status": "OBSERVED"})
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
            svg = chart.render(rows, ["asg.desired"], "Synthetic")
        self.assertIn("<polyline", svg)
        self.assertIn("Synthetic", svg)
        overview = chart.render_overview(rows)
        self.assertIn("EC2 capacity", overview)
        self.assertIn("asg.desired", overview)
        self.assertGreaterEqual(overview.count("<polyline"), 3)
        self.assertIn("ecs.api.desired (missing)", overview)

    def test_chart_does_not_bridge_missing_sample(self):
        rows = [{"sample_at": f"2026-11-19T00:0{i}:00Z", "metric": "asg.desired",
                 "value": "" if i == 1 else "3", "status": "MISSING" if i == 1 else "OBSERVED"}
                for i in range(3)]
        svg = chart.render(rows, ["asg.desired"], "Gap")
        self.assertEqual(svg.count("<polyline"), 2)
        self.assertEqual(svg.count("<circle"), 2)
        overview = chart.render_overview(rows)
        self.assertEqual(overview.count("<polyline"), 2)


if __name__ == "__main__":
    unittest.main()
