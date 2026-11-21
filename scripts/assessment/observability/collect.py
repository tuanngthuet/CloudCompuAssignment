"""C1 read-only AWS snapshot collector. Python 3.9+ and AWS CLI v2; no pip packages."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

UTC = dt.timezone.utc
FIELDS = ["sample_at", "metric", "value", "unit", "source_at", "status"]
ACTIVITY_FIELDS = ["observed_at", "source", "activity_id", "start_at", "end_at",
                   "status", "description", "cause"]


def now():
    return dt.datetime.now(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def error_code(stderr):
    match = re.search(r"\(([A-Za-z0-9_.-]+)\)", stderr)
    return match.group(1) if match else "AWS_CLI_ERROR"


class AWS:
    def __init__(self, profile, region):
        self.profile, self.region = profile, region
        self.errors = []

    def call(self, service, operation, *options, input_data=None):
        command = ["aws", service, operation, "--profile", self.profile, "--region", self.region,
                   "--output", "json", "--no-cli-pager", "--cli-connect-timeout", "5",
                   "--cli-read-timeout", "15", *options]
        if input_data is not None:
            command += ["--cli-input-json", "file://" + str(input_data)]
        env = dict(os.environ, AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off", AWS_MAX_ATTEMPTS="2")
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=45, env=env, shell=False)
            if result.returncode:
                raise RuntimeError(error_code(result.stderr))
            return json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
            code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            self.errors.append({"api": service + "." + operation, "code": code, "at": iso(now())})
            return None


def resource_value(resources, name):
    for item in resources or []:
        if item.get("name") == name:
            return item.get("integerValue", item.get("longValue"))
    return None


def add(rows, stamp, name, value, unit="Count", source=None, status=None):
    rows.append({"sample_at": stamp, "metric": name, "value": "" if value is None else value,
                 "unit": unit, "source_at": stamp if source is None else source,
                 "status": status or ("MISSING" if value is None else "OBSERVED")})


def describe(aws, args, rows, stamp):
    services = aws.call("ecs", "describe-services", "--cluster", args.cluster,
                        "--services", args.api_service, args.worker_service, args.publisher_service) or {}
    matched = {s["serviceName"]: s for s in services.get("services", [])}
    for label, name in (("api", args.api_service), ("worker", args.worker_service),
                        ("publisher", args.publisher_service)):
        service = matched.get(name, {})
        for key, field in (("desired", "desiredCount"), ("running", "runningCount"),
                           ("pending", "pendingCount")):
            add(rows, stamp, "ecs." + label + "." + key, service.get(field))
    group = (aws.call("autoscaling", "describe-auto-scaling-groups",
                      "--auto-scaling-group-names", args.asg) or {}).get("AutoScalingGroups", [])
    group = group[0] if group else {}
    for key, field in (("desired", "DesiredCapacity"), ("min", "MinSize"), ("max", "MaxSize")):
        add(rows, stamp, "asg." + key, group.get(field))
    instances = group.get("Instances", [])
    add(rows, stamp, "asg.in_service", sum(i.get("LifecycleState") == "InService" for i in instances)
        if group else None)
    add(rows, stamp, "asg.healthy", sum(i.get("HealthStatus") == "Healthy" for i in instances)
        if group else None)
    target = aws.call("elbv2", "describe-target-health", "--target-group-arn", args.target_group) or {}
    targets = target.get("TargetHealthDescriptions")
    add(rows, stamp, "alb.healthy_targets", sum(t.get("TargetHealth", {}).get("State") == "healthy"
                                                  for t in targets) if targets is not None else None)
    add(rows, stamp, "alb.unhealthy_targets", sum(t.get("TargetHealth", {}).get("State") == "unhealthy"
                                                    for t in targets) if targets is not None else None)
    listed = aws.call("ecs", "list-container-instances", "--cluster", args.cluster) or {}
    arns = listed.get("containerInstanceArns", [])
    containers = []
    if arns:
        data = aws.call("ecs", "describe-container-instances", "--cluster", args.cluster,
                        "--container-instances", *arns) or {}
        containers = data.get("containerInstances", [])
    add(rows, stamp, "ecs.registered_instances", len(containers) if listed else None)
    az_totals = {}
    for item in containers:
        zone = item.get("attributes", [])
        zone = next((a.get("value") for a in zone if a.get("name") == "ecs.availability-zone"), "unknown")
        suffix = zone.replace("ap-southeast-2", "az_")
        totals = az_totals.setdefault(suffix, {"instances": 0, "running_tasks": 0,
                                             "memory": 0, "eni": 0,
                                             "running_tasks_known": True,
                                             "memory_known": True, "eni_known": True})
        totals["instances"] += 1
        running_tasks = item.get("runningTasksCount")
        if running_tasks is None:
            totals["running_tasks_known"] = False
        else:
            totals["running_tasks"] += running_tasks
        for key, field in (("memory_remaining_mb", "MEMORY"), ("eni_remaining", "ENI")):
            value = resource_value(item.get("remainingResources"), field)
            label = "memory" if field == "MEMORY" else "eni"
            if value is None:
                totals[label + "_known"] = False
            else:
                totals[label] += value
    for zone, totals in az_totals.items():
        add(rows, stamp, "ecs." + zone + ".instances", totals["instances"])
        add(rows, stamp, "ecs." + zone + ".running_tasks",
            totals["running_tasks"] if totals["running_tasks_known"] else None)
        add(rows, stamp, "ecs." + zone + ".memory_remaining_mb",
            totals["memory"] if totals["memory_known"] else None, "MiB")
        add(rows, stamp, "ecs." + zone + ".eni_remaining",
            totals["eni"] if totals["eni_known"] else None)
    return matched, group, containers


def cloudwatch(aws, args, rows, stamp, dest, instance_ids=None):
    specs = [
        ("ecs.cpu_percent", "AWS/ECS", "CPUUtilization", {"ClusterName": args.cluster, "ServiceName": args.api_service}, "Average"),
        ("ecs.memory_percent", "AWS/ECS", "MemoryUtilization", {"ClusterName": args.cluster, "ServiceName": args.api_service}, "Average"),
        ("ecs.running_tasks_cw", "ECS/ContainerInsights", "RunningTaskCount", {"ClusterName": args.cluster, "ServiceName": args.api_service}, "Average"),
        ("ecs.pending_tasks_cw", "ECS/ContainerInsights", "PendingTaskCount", {"ClusterName": args.cluster, "ServiceName": args.api_service}, "Average"),
        ("ecs.capacity_reservation", "AWS/ECS/ManagedScaling", "CapacityProviderReservation", {"ClusterName": args.cluster, "CapacityProviderName": args.capacity_provider}, "Average"),
        ("ec2.cpu_percent", "AWS/EC2", "CPUUtilization", {"AutoScalingGroupName": args.asg}, "Average"),
        ("asg.desired_cw", "AWS/AutoScaling", "GroupDesiredCapacity", {"AutoScalingGroupName": args.asg}, "Average"),
        ("asg.in_service_cw", "AWS/AutoScaling", "GroupInServiceInstances", {"AutoScalingGroupName": args.asg}, "Average"),
        ("alb.request_count", "AWS/ApplicationELB", "RequestCount", {"LoadBalancer": args.alb_suffix}, "Sum"),
        ("alb.target_response_seconds", "AWS/ApplicationELB", "TargetResponseTime", {"LoadBalancer": args.alb_suffix, "TargetGroup": args.target_group_suffix}, "p95"),
        ("alb.target_4xx", "AWS/ApplicationELB", "HTTPCode_Target_4XX_Count", {"LoadBalancer": args.alb_suffix, "TargetGroup": args.target_group_suffix}, "Sum"),
        ("alb.5xx", "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", {"LoadBalancer": args.alb_suffix, "TargetGroup": args.target_group_suffix}, "Sum"),
        ("alb.elb_4xx", "AWS/ApplicationELB", "HTTPCode_ELB_4XX_Count", {"LoadBalancer": args.alb_suffix}, "Sum"),
        ("alb.elb_5xx", "AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", {"LoadBalancer": args.alb_suffix}, "Sum"),
        ("alb.healthy_cw", "AWS/ApplicationELB", "HealthyHostCount", {"LoadBalancer": args.alb_suffix, "TargetGroup": args.target_group_suffix}, "Minimum"),
        ("rds.connections", "AWS/RDS", "DatabaseConnections", {"DBInstanceIdentifier": args.db}, "Maximum"),
        ("rds.cpu_percent", "AWS/RDS", "CPUUtilization", {"DBInstanceIdentifier": args.db}, "Average"),
        ("rds.read_latency_seconds", "AWS/RDS", "ReadLatency", {"DBInstanceIdentifier": args.db}, "Average"),
        ("rds.write_latency_seconds", "AWS/RDS", "WriteLatency", {"DBInstanceIdentifier": args.db}, "Average"),
        ("app.queue_wait_ms", "LabSeat/Application", "QueueWaitMs", {}, "p95"),
        ("app.redis_latency_ms", "LabSeat/Application", "RedisLatencyMs", {}, "p95"),
        ("app.outbox_pending", "LabSeat/Application", "OutboxPending", {}, "Maximum"),
    ]
    for label, cache_id in (("node_1", args.cache_cluster),
                            ("node_2", args.cache_cluster_replica)):
        if not cache_id:
            continue
        for name, metric in (("connections", "CurrConnections"),
                             ("cpu_percent", "EngineCPUUtilization"),
                             ("freeable_memory_bytes", "FreeableMemory")):
            specs.append(("redis." + label + "." + name, "AWS/ElastiCache", metric,
                          {"CacheClusterId": cache_id}, "Average"))
    for instance_id in sorted(set(args.instance_ids + (instance_ids or []))):
        specs.append(("ec2." + instance_id + ".cpu_credits", "AWS/EC2", "CPUCreditBalance",
                      {"InstanceId": instance_id}, "Average"))
    for label, queue in (("queue", args.queue), ("dlq", args.dlq)):
        if queue:
            for name, stat in (("ApproximateNumberOfMessagesVisible", "Maximum"),
                               ("ApproximateAgeOfOldestMessage", "Maximum")):
                specs.append((label + "." + name, "AWS/SQS", name, {"QueueName": queue}, stat))
    queries = [{"Id": "m" + str(i), "MetricStat": {"Metric": {"Namespace": ns, "MetricName": metric,
                 "Dimensions": [{"Name": k, "Value": v} for k, v in dimensions.items()]},
                 "Period": 60, "Stat": stat}, "ReturnData": True}
               for i, (_, ns, metric, dimensions, stat) in enumerate(specs)]
    end = now()
    payload = {"StartTime": iso(end - dt.timedelta(minutes=8)), "EndTime": iso(end),
               "MetricDataQueries": queries, "ScanBy": "TimestampDescending"}
    request_dir = dest / "metric-requests"
    request_dir.mkdir(exist_ok=True)
    input_file = request_dir / ("metric-request-" + stamp.replace(":", "").replace("-", "") + ".json")
    input_file.write_text(json.dumps(payload), encoding="utf-8")
    result = aws.call("cloudwatch", "get-metric-data", input_data=input_file) or {}
    found = {m["Id"]: m for m in result.get("MetricDataResults", [])}
    for i, (name, _, _, _, _) in enumerate(specs):
        series = found.get("m" + str(i), {})
        timestamps, values = series.get("Timestamps", []), series.get("Values", [])
        unit = ("Percent" if name.endswith("_percent") or name == "ecs.capacity_reservation"
                else "Bytes" if name.endswith("_bytes")
                else "Seconds" if name.endswith("_seconds") or name.endswith("ReadLatency")
                or name.endswith("WriteLatency") or name.endswith("ApproximateAgeOfOldestMessage")
                else "Milliseconds" if name.endswith("_ms") else "Count")
        add(rows, stamp, name, values[0] if values else None, unit=unit,
            source=timestamps[0] if timestamps else "",
            status="OBSERVED" if values else "MISSING_OR_DELAYED")
        if name == "alb.request_count":
            add(rows, stamp, "alb.rps", round(values[0] / 60, 4) if values else None,
                unit="Requests/second", source=timestamps[0] if timestamps else "",
                status="OBSERVED" if values else "MISSING_OR_DELAYED")


def scaling_activities(aws, args, stamp, seen):
    """Collect new ECS and ASG scaling events; keep raw causes private."""
    sources = [
        ("asg", "autoscaling", "describe-scaling-activities",
         ("--auto-scaling-group-name", args.asg), "Activities"),
        ("ecs", "application-autoscaling", "describe-scaling-activities",
         ("--service-namespace", "ecs", "--resource-id",
          "service/" + args.cluster + "/" + args.api_service), "ScalingActivities"),
    ]
    rows = []
    for label, service, operation, options, field in sources:
        data = aws.call(service, operation, *options) or {}
        for activity in data.get(field, []):
            activity_id = activity.get("ActivityId") or activity.get("ActivityID")
            key = (label, activity_id or str(activity.get("StartTime")) + str(activity.get("Description")),
                   activity.get("StatusCode"), str(activity.get("EndTime")))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"observed_at": stamp, "source": label, "activity_id": activity_id or "",
                         "start_at": str(activity.get("StartTime", "")),
                         "end_at": str(activity.get("EndTime", "")),
                         "status": activity.get("StatusCode", ""),
                         "description": activity.get("Description", ""),
                         "cause": activity.get("Cause", "")})
    return rows


def preflight(aws, args, dest):
    report = {"collected_at": iso(now()), "region": args.region, "cluster": args.cluster,
              "status": "NOT_REVIEWED", "checks": {}}
    identity = aws.call("sts", "get-caller-identity") or {}
    report["checks"]["account_match"] = identity.get("Account") == args.expected_account
    if not report["checks"]["account_match"]:
        report["status"] = "BLOCKED_ACCOUNT"
        (dest / "preflight.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError("Account unavailable or mismatch; stopped before resource collection")
    report["checks"]["db_max_connections"] = "NOT_VERIFIED: needs read-only SQL in VPC"
    report["checks"]["db_budget"] = args.db_budget
    report["checks"]["runner"] = "NOT_VERIFIED: record CPU/network during k6 smoke on external runner"
    report["checks"]["restore_quota"] = "NOT_VERIFIED: confirm quotas and temporary resource headroom with B4"
    report["checks"]["other_az_capacity"] = "REVIEW ecs AZ remaining MEMORY/ENI with C4 before fault"
    report["checks"]["schema_revision"] = "NOT_VERIFIED: compare app/DB release in VPC"
    report["checks"]["redis_metric_nodes"] = {"node_1": args.cache_cluster,
                                                "node_2": args.cache_cluster_replica or None}
    providers = aws.call("ecs", "describe-capacity-providers", "--capacity-providers",
                         args.capacity_provider) or {}
    report["checks"]["capacity_provider"] = [
        {"name": item.get("name"), "status": item.get("status"),
         "asg": item.get("autoScalingGroupProvider", {}).get("autoScalingGroupArn"),
         "managed_scaling": item.get("autoScalingGroupProvider", {}).get("managedScaling", {}).get("status")}
        for item in providers.get("capacityProviders", [])]
    rds = aws.call("rds", "describe-db-instances", "--db-instance-identifier", args.db) or {}
    databases = rds.get("DBInstances", [])
    if databases:
        db = databases[0]
        report["checks"]["rds"] = {k: db.get(k) for k in ("DBInstanceStatus", "MultiAZ",
                                  "BackupRetentionPeriod", "LatestRestorableTime")}
    attributes = aws.call("rds", "describe-account-attributes") or {}
    report["checks"]["rds_account_quotas"] = [
        {"name": item.get("AccountQuotaName"), "max": item.get("Max"), "used": item.get("Used")}
        for item in attributes.get("AccountQuotas", []) if item.get("AccountQuotaName") in
        ("DBInstances", "DBSnapshots", "TotalStorage")]
    services = aws.call("ecs", "describe-services", "--cluster", args.cluster,
                        "--services", args.api_service, args.worker_service, args.publisher_service) or {}
    found = {s.get("serviceName"): s for s in services.get("services", [])}
    report["checks"]["services"] = {name: {"desired": found.get(name, {}).get("desiredCount"),
                                                   "running": found.get(name, {}).get("runningCount"),
                                                   "pending": found.get(name, {}).get("pendingCount"),
                                                   "rollout": [d.get("rolloutState") for d in
                                                               found.get(name, {}).get("deployments", [])]}
                                    for name in (args.api_service, args.worker_service, args.publisher_service)}
    tasks = aws.call("ecs", "list-tasks", "--cluster", args.cluster,
                     "--service-name", args.api_service) or {}
    task_arns = tasks.get("taskArns", [])
    if task_arns:
        details = aws.call("ecs", "describe-tasks", "--cluster", args.cluster,
                           "--tasks", *task_arns) or {}
        report["checks"]["api_tasks"] = [{"az": t.get("availabilityZone"),
                                            "status": t.get("lastStatus"),
                                            "health": t.get("healthStatus"),
                                            "digest": c.get("imageDigest")}
                                           for t in details.get("tasks", []) for c in t.get("containers", [])]
        digests = {t["digest"] for t in report["checks"]["api_tasks"] if t["digest"]}
        report["checks"]["same_api_digest"] = len(digests) == 1 and len(report["checks"]["api_tasks"]) == len(task_arns)
    target = aws.call("elbv2", "describe-target-health", "--target-group-arn", args.target_group) or {}
    report["checks"]["healthy_targets"] = sum(t.get("TargetHealth", {}).get("State") == "healthy"
                                                for t in target.get("TargetHealthDescriptions", [])) if target else None
    group = (aws.call("autoscaling", "describe-auto-scaling-groups",
                      "--auto-scaling-group-names", args.asg) or {}).get("AutoScalingGroups", [])
    if group:
        g = group[0]
        report["checks"]["asg"] = {"min": g.get("MinSize"), "max": g.get("MaxSize"),
                                    "desired": g.get("DesiredCapacity"),
                                    "in_service": sum(i.get("LifecycleState") == "InService" for i in g.get("Instances", [])),
                                    "suspended_processes": [p.get("ProcessName") for p in g.get("SuspendedProcesses", [])]}
    for label, url in (("queue", args.queue_url), ("dlq", args.dlq_url)):
        if url:
            data = aws.call("sqs", "get-queue-attributes", "--queue-url", url,
                            "--attribute-names", "ApproximateNumberOfMessages",
                            "ApproximateNumberOfMessagesNotVisible", "RedrivePolicy", "VisibilityTimeout") or {}
            attrs = data.get("Attributes", {})
            report["checks"][label] = {"visible": attrs.get("ApproximateNumberOfMessages"),
                                        "in_flight": attrs.get("ApproximateNumberOfMessagesNotVisible"),
                                        "visibility_timeout": attrs.get("VisibilityTimeout"),
                                        "redrive_configured": "RedrivePolicy" in attrs}
    if args.sns_topic:
        subscriptions = aws.call("sns", "list-subscriptions-by-topic", "--topic-arn", args.sns_topic) or {}
        report["checks"]["sns_confirmed_subscriptions"] = sum(
            s.get("SubscriptionArn") != "PendingConfirmation"
            for s in subscriptions.get("Subscriptions", []))
    alarms = aws.call("cloudwatch", "describe-alarms", "--alarm-name-prefix", args.alarm_prefix) or {}
    report["checks"]["alarms"] = [{"name": a.get("AlarmName"), "state": a.get("StateValue"),
                                      "actions_enabled": a.get("ActionsEnabled")}
                                     for a in alarms.get("MetricAlarms", [])]
    report["status"] = "COLLECTED_REVIEW_REQUIRED"
    (dest / "preflight.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "expected-account", "cluster", "api-service", "worker-service",
                 "publisher-service", "asg", "target-group", "target-group-suffix", "alb-suffix",
                 "capacity-provider", "db", "cache-cluster"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--cache-cluster-replica", default="",
                        help="second ElastiCache node ID; labels remain stable across role switch")
    parser.add_argument("--queue", default="")
    parser.add_argument("--dlq", default="")
    parser.add_argument("--queue-url", default="")
    parser.add_argument("--dlq-url", default="")
    parser.add_argument("--sns-topic", default="")
    parser.add_argument("--instance-ids", nargs="*", default=[])
    parser.add_argument("--alarm-prefix", default="labseat-")
    parser.add_argument("--db-budget", type=int, default=66)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--samples", type=int, default=1)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{12}", args.expected_account) or args.interval < 15 or args.interval > 30 or args.samples < 1:
        parser.error("expected-account must be 12 digits; interval 15–30 seconds; samples >= 1")
    root = Path(__file__).resolve().parents[3]
    runtime_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                    capture_output=True, text=True).stdout.strip()
    runtime_collector_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".local/assessment/check"]).returncode:
        parser.error(".local/ must be Git-ignored")
    run_id = now().strftime("%Y%m%dT%H%M%SZ") + "-C1-" + os.urandom(3).hex()
    dest = root / ".local" / "assessment" / run_id
    dest.mkdir(parents=True, exist_ok=False)
    aws = AWS(args.profile, args.region)
    failed = False
    try:
        preflight(aws, args, dest)
        with (dest / "metrics.csv").open("w", newline="", encoding="utf-8") as handle, \
             (dest / "activities.csv").open("w", newline="", encoding="utf-8") as activity_handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            activity_writer = csv.DictWriter(activity_handle, fieldnames=ACTIVITY_FIELDS)
            writer.writeheader()
            activity_writer.writeheader()
            seen_activities = set()
            for sample in range(args.samples):
                start = time.monotonic()
                rows = []
                stamp = iso(now())
                phase_start = time.monotonic()
                _, group, _ = describe(aws, args, rows, stamp)
                add(rows, stamp, "collector.describe_seconds",
                    round(time.monotonic() - phase_start, 2), "Seconds")
                instance_ids = [i["InstanceId"] for i in group.get("Instances", []) if i.get("InstanceId")]
                phase_start = time.monotonic()
                cloudwatch(aws, args, rows, stamp, dest, instance_ids)
                add(rows, stamp, "collector.cloudwatch_seconds",
                    round(time.monotonic() - phase_start, 2), "Seconds")
                phase_start = time.monotonic()
                activity_writer.writerows(scaling_activities(aws, args, stamp, seen_activities))
                add(rows, stamp, "collector.activities_seconds",
                    round(time.monotonic() - phase_start, 2), "Seconds")
                activity_handle.flush()
                elapsed = time.monotonic() - start
                add(rows, stamp, "collector.duration_seconds", round(elapsed, 2), "Seconds",
                    status="OVER_INTERVAL" if elapsed > args.interval else "OBSERVED")
                writer.writerows(rows)
                handle.flush()
                print("sample", sample + 1, "at", stamp, "rows", len(rows), flush=True)
                if sample + 1 < args.samples:
                    time.sleep(max(0, args.interval - elapsed))
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(str(exc), file=sys.stderr)
        failed = True
    finally:
        (dest / "manifest.json").write_text(json.dumps({"task_id": "C1", "run_id": run_id,
             "region": args.region, "source_commit": runtime_commit,
             "collector_sha256": runtime_collector_sha256,
             "errors": aws.errors,
             "privacy": "PRIVATE; review before publishing"}, indent=2) + "\n", encoding="utf-8")
        metric_file = dest / "metrics.csv"
        counts = {}
        if metric_file.exists():
            with metric_file.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    counts[row["status"]] = counts.get(row["status"], 0) + 1
        lines = ["# C1 private collection summary", "", "Collection is not acceptance PASS.", "",
                 "- Run ID: `" + run_id + "`", "- Collected metric rows: " + str(sum(counts.values())),
                 "- Status counts: " + json.dumps(counts, sort_keys=True),
                 "- AWS API errors: " + str(len(aws.errors)), ""]
        lines += ["- " + e["api"] + ": " + e["code"] for e in aws.errors]
        (dest / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Private run:", dest)
    return 2 if aws.errors or failed else 0


if __name__ == "__main__":
    sys.exit(main())
