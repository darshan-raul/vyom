import os
from fastmcp import FastMCP

mcp = FastMCP("vyom-mcp")

@mcp.tool()
async def get_costs(
    start_date: str | None = None,
    end_date: str | None = None,
    service: str | None = None,
    granularity: str = "DAILY",
    tenant_id: str | None = None,
) -> str:
    """Query AWS Cost Explorer for cost and usage data.
    
    Args:
        start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
        end_date: End date (YYYY-MM-DD), defaults to today
        service: Filter by AWS service name (e.g., 'Amazon EC2', 'Amazon S3')
        granularity: DAILY, MONTHLY, or HOURLY
        tenant_id: Tenant identifier (injected from session)
    """
    from datetime import datetime, timedelta
    import json

    if not tenant_id:
        return json.dumps({"error": "tenant_id required"})

    creds = _get_tenant_credentials(tenant_id)
    if not creds:
        return json.dumps({"error": "no credentials for tenant"})

    import boto3
    client = boto3.client(
        "ce",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        region_name=creds.get("region", "us-east-1")
    )

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    params = {
        "TimePeriod": {"Start": start_date, "End": end_date},
        "Granularity": granularity,
        "Metrics": ["UnblendedCost", "BlendedCost", "UsageQuantity"],
    }
    if service:
        params["Filter"] = {"Dimensions": {"Key": "SERVICE", "Values": [service]}}

    response = client.get_cost_and_usage(**params)
    results = []
    for page in response.get("ResultsByTime", []):
        period = page["TimePeriod"]
        for key, value in page["Total"].items():
            results.append({
                "period_start": period["Start"],
                "period_end": period["End"],
                "metric": key,
                "value": value
            })
    return json.dumps({"tenant_id": tenant_id, "period": {"start": start_date, "end": end_date}, "data": results})


@mcp.tool()
async def get_resources(
    resource_types: list[str] | None = None,
    region: str | None = None,
    tenant_id: str | None = None,
) -> str:
    """List AWS resources (EC2, S3, RDS) for a tenant.
    
    Args:
        resource_types: List of types to fetch ['ec2', 's3', 'rds'], defaults to all
        region: AWS region, defaults to tenant's default region
        tenant_id: Tenant identifier (injected from session)
    """
    import json
    if not tenant_id:
        return json.dumps({"error": "tenant_id required"})

    creds = _get_tenant_credentials(tenant_id)
    if not creds:
        return json.dumps({"error": "no credentials for tenant"})

    import boto3
    session = boto3.Session(
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        region_name=region or creds.get("region", "us-east-1")
    )

    results = []
    types = resource_types or ["ec2", "s3", "rds"]

    if "ec2" in types:
        try:
            ec2 = session.client("ec2")
            resp = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["running"]}])
            for reservation in resp.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    results.append({
                        "type": "ec2", "id": instance["InstanceId"],
                        "state": instance["State"]["Name"],
                        "tags": {t["Key"]: t["Value"] for t in instance.get("Tags", [])},
                        "region": instance["Placement"]["AvailabilityZone"]
                    })
        except Exception:
            pass

    if "s3" in types:
        try:
            s3 = session.client("s3")
            resp = s3.list_buckets()
            for bucket in resp.get("Buckets", []):
                results.append({
                    "type": "s3", "id": bucket["Name"],
                    "created": bucket["CreationDate"].isoformat(), "region": "global"
                })
        except Exception:
            pass

    if "rds" in types:
        try:
            rds = session.client("rds")
            resp = rds.describe_db_instances()
            for db in resp.get("DBInstances", []):
                results.append({
                    "type": "rds", "id": db["DBInstanceIdentifier"],
                    "engine": db["Engine"], "state": db["DBInstanceStatus"],
                    "region": db["AvailabilityZone"]
                })
        except Exception:
            pass

    return json.dumps({"tenant_id": tenant_id, "count": len(results), "resources": results[:100]})


TENANT_SECRETS_DIR = os.getenv("TENANT_SECRETS_DIR", "/etc/secrets/tenants")


def _get_tenant_credentials(tenant_id: str) -> dict | None:
    import json
    secret_path = os.path.join(TENANT_SECRETS_DIR, tenant_id, "aws.json")
    if os.path.exists(secret_path):
        with open(secret_path) as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.app, host="0.0.0.0", port=8000)
