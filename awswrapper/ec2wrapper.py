import sys
import re
import boto3
from collections import defaultdict

def get_ec2_connection():
    try:
        return boto3.client('ec2')
    except Exception as e:
        sys.exit('Error connecting to EC2 check your AWS credentials!')


def get_route53_connection():
    try:
        return boto3.client('route53')
    except Exception as e:
        sys.exit('Error connecting to route53 check your AWS credentials!')


def get_ec2_resource():
    try:
        return boto3.resource('ec2')
    except Exception as e:
        sys.exit('Error getting EC2 Resource!')


def get_instances_ids(ec2_instances):
    instance_ids = []

    for reservation in ec2_instances['Reservations']:
        for instance in reservation['Instances']:
            instance_ids.append(instance['InstanceId'])

    return instance_ids


def get_instances_data(ec2_instances, filter_by_state=False):
    instances = defaultdict(list) if filter_by_state else []
    for reservation in ec2_instances['Reservations']:
        for instance in reservation['Instances']:
            instance_data = {}
            instance_tags = get_tags_from_instance(instance=instance)
            instance_data.update(instance_tags)
            instance_data.update(instance)
            if filter_by_state:
                instance_state = 'running' if instance_data['State']['Name'] == 'running' else 'not-running'
                instances[instance_state].append(instance_data)
            else:
                instances.append(instance_data)
    return instances


def get_tags_from_instance(instance):
    instances_data_tags = {}
    if "Tags" in instance:
        for tag in instance['Tags']:
            tag_name = tag['Key']
            tag_value = tag['Value']

            # Check only tags with a value set
            if tag_value is not None:
                instances_data_tags[tag_name] = tag_value

    return instances_data_tags


# Returns a dictionary with Instance information
def list_instances_without_tag(tags_filter, ec2_instances):
    instances_without_tags = []

    for reservation in ec2_instances['Reservations']:
        for instance in reservation['Instances']:
            instance_tags = get_tags_from_instance(instance=instance)
            instance_data = {}
            if not are_any_filter_tags_on_instance(tags_filter, instance_tags):
                instance_data['InstanceId'] = instance['InstanceId']
                instance_data['Name'] = instance_tags['Name'] if "Name" in instance_tags else ''
                instances_without_tags.append(instance_data)

    return instances_without_tags


def are_any_filter_tags_on_instance(tags_filter, instances_tags):
    for filter_tag in tags_filter.keys():
        filtered_tag_in_instance = instances_tags.get(filter_tag, '')
        pattern = tags_filter.get(filter_tag)
        tags_values_match = re.search(pattern, filtered_tag_in_instance)
        if filtered_tag_in_instance and tags_values_match:
            return True

    return False


def delete_ip_record_set(record_name, record_value, zone_id, ttl):
    client = get_route53_connection()
    try:
        return client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Comment': 'Remove Record Set',
                'Changes': [
                    {
                        'Action': 'DELETE',
                        'ResourceRecordSet': {
                            'Name': record_name,
                            'Type': 'A',
                            'TTL': ttl,
                            'ResourceRecords': [
                                {
                                    'Value': record_value
                                },
                            ],
                        }
                    }
                ]
            }
        )
    except Exception as e:
        print "Cannot Remove Record Set: {}".format(e.message)
        pass


def start_instances(instance_ids, dry_run=False):
    ec2 = get_ec2_connection()

    try:
        return ec2.start_instances(
            InstanceIds=instance_ids,
            DryRun=dry_run
        )
    except Exception as e:
        sys.exit("Error starting instances!\n {0}".format(e.message))


def stop_instances(instance_ids, dry_run=False):
    ec2 = get_ec2_connection()

    try:
        return ec2.stop_instances(
            InstanceIds=instance_ids,
            DryRun=dry_run,
            Force=False
        )
    except Exception as e:
        sys.exit("Error stopping instances!\n {0}".format(e.message))


def terminate_instances(instance_ids, dry_run=False):
    ec2 = get_ec2_connection()

    try:
        return ec2.terminate_instances(
            InstanceIds=instance_ids,
            DryRun=dry_run
        )
    except Exception as e:
        sys.exit("Error terminating instances!\n {0}".format(e.message))


def describe_instances(state=None):
    filters = []
    if state is not None:
        filters.append(
            {
                'Name': 'instance-state-name',
                'Values': [state]
            }
        )

    ec2 = get_ec2_connection()
    ec2_response = ec2.describe_instances(
        Filters=filters,
    )

    if "Reservations" not in ec2_response:
        sys.exit("Error talking with AWS - No 'Reservations' key in Response")

    return ec2_response


def describe_instances_by_ids(instance_ids):
    ec2 = get_ec2_connection()
    ec2_response = ec2.describe_instances(
        InstanceIds=instance_ids,
    )

    if "Reservations" not in ec2_response:
        sys.exit("Error talking with AWS - No 'Reservations' key in Response")

    return ec2_response


def describe_instances_by_tag(tag, value=None, state=None):
    tag_key = "tag:{0}".format(tag)
    tag_value = value if value else '*'

    filters = [
        {
            'Name': tag_key,
            'Values': [tag_value]
        }
    ]

    if state is not None:
        filters.append(
            {
                'Name': 'instance-state-name',
                'Values': [state]
            }
        )

    ec2 = get_ec2_connection()
    ec2_response = ec2.describe_instances(
        Filters=filters,
    )

    if "Reservations" not in ec2_response:
        sys.exit("Error talking with AWS - No 'Reservations' key in Response")

    return ec2_response


def describe_instances_by_tag_filters(tag_filters, state=None):
    filters = tag_filters

    if state is not None:
        filters.append(
            {
                'Name': 'instance-state-name',
                'Values': [state]
            }
        )

    ec2 = get_ec2_connection()
    ec2_response = ec2.describe_instances(
        Filters=filters,
    )

    if "Reservations" not in ec2_response:
        sys.exit("Error talking with AWS - No 'Reservations' key in Response")

    return ec2_response


def create_snapshot_from_volume(snapshot_name, description, volume_id):
    ec2 = get_ec2_resource()

    try:
        snapshot = ec2.create_snapshot(VolumeId=volume_id, Description=description)
        snapshot.create_tags(
            DryRun=False,
            Tags=[
                {
                    'Key': 'Name',
                    'Value': snapshot_name
                },
            ]
        )
        return snapshot
    except Exception as e:
        sys.exit("Error Creating snapshot!\n {0}".format(e.message))
