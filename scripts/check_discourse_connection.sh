#!/bin/bash
# This script allows to test whether the connection with Discourse works.
# It takse the v6 user id as only parameter.

# The api key must be in Discourse api_keys table and created by user -1.
# SSO users must be available in Discourse single_sign_on_records table.
# The Discourse (internal url and api key must be in common.ini.

# Extract a value from an ini file
function ini
{
  awk -F "=" '/'$1'/ {print $2}' common.ini | tr -d ' '
}

id=${1:-2}
api_key=$(ini 'discourse.api_key')
discourse_url=$(ini 'discourse.url')

url="$discourse_url//users/by-external/$id.json?api_key=$api_key&api_username=system"
echo "Discourse url: $discourse_url"
echo "API key: $api_key"
echo "v6 user id: $id"
echo
echo "Test URL: $url"

# The reply should be 200 OK
curl -vv $url
