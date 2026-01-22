#!/bin/bash
# shellcheck disable=SC2001

# this scripts is meant to be executed whenever navitia france coverages are updated.
# the goal of this script is to save in DB france coverages, with their id and geometry.
# there are as many Navitia request as there are coverages in France.
# 
# The script takes in parameter
# Username 'user123'
# Password 'password123' (make sure to escape special characters)
# Base API URL 'http://localhost'
# API Port '6543'
# And is meant to be used by moderators, as regular users can't delete documents.

# First, a token is retrieved using username and password in parameter.
# Then, existing coverages are deleted
# Navitia request are made towards /coverages/{region_id} route to get all coverages.
# For each coverage found, a POST on Base_API_URL:API_PORT/coverages is made to insert in database. 

# NOTE: the geometry returned by Navitia for the coverages are in WGS384.

# Function to display usage
usage() {
    echo "Usage: $0 <username> <password> <base_api_url> <api_port>"
    exit 1
}

# Check if exactly 4 arguments are provided
if [ "$#" -ne 4 ]; then
    usage
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "jq could not be found. Please install it."
    exit 1
fi

# Assign arguments to variables
username="$1"
password="$2"
base_api_url="$3"
api_port="$4"

LOG_FILE="log-navitia-coverage.txt"
NAVITIA_REQUEST_COUNT=0

COVERAGE_API_URL="$base_api_url:$api_port/coverages" 

echo "Start time :" > "$LOG_FILE"
echo $(date +"%Y-%m-%d-%H-%M-%S") >> "$LOG_FILE"

login_body=$(jq -n \
        --arg username "$username" \
        --arg password "$password" \
        '{
            username: $username,
            password: $password,
            discourse: true,
        }')

# log in to execute script
loginResponse=$(curl -s -X POST "$base_api_url:$api_port/users/login" \
        -H "Content-Type: application/json" \
        -d "$login_body")

roles=$(echo "$loginResponse" | jq -r '.roles')
JWTToken=$(echo "$loginResponse" | jq -r '.token')

coverages=$(curl -s -X GET "$COVERAGE_API_URL" \
    -H "Content-Type: application/json")

numberOfCoverage=$(echo "$coverages" | jq -r '.total')

if [ "$numberOfCoverage" != "0" ]; then
    # check if logged user is a moderator
    found=false
    for role in "${roles[@]}"; do
        if [[ "$role" == "moderator" ]]; then
            found=true
            break
        fi
    done
    if ! $found; then
        echo "Error : User should be a moderator to delete existing coverages"
        exit 1
    fi

    # remove old coverages
    echo "$coverages" | jq -c '.documents[]' | while IFS= read -r coverage; do
        coverage_doc_id=$(echo "$coverage" | jq -r '.document_id')

        deleteResponse=$(curl -X POST -v -H "Content-Type: application/json" -H "Authorization: JWT token=\"$JWTToken\"" "$base_api_url:$api_port/documents/delete/${coverage_doc_id}")

        status=$(echo "$deleteResponse" | jq -r '.status')

        # if we can't delete coverage, then we stop the script
        if [ "$status" = "error" ]; then
            exit 1
        fi
    done
fi

# This define how much navitia request will be made executing this script
regions=('fr-idf' 'fr-ne' 'fr-nw' 'fr-se' 'fr-sw')

responses=()

# Loop over Navitia regions in France
for region_id in "${regions[@]}"; do
    # Fetch the response from the Navitia API
    response=$(curl -s -H "Authorization: $NAVITIA_API_KEY" \
        "https://api.navitia.io/v1/coverage/${region_id}")
    ((NAVITIA_REQUEST_COUNT++))

    # Extract the coverage type
    coverage_type=$(echo "$response" | jq -r '.regions[0].id')

    # Extract the shape (WKT string)
    shape=$(echo "$response" | jq -r '.regions[0].shape')

    # remove 'MULTIPOLGYON' from shape
    coordinate_list=${shape//"MULTIPOLYGON"/}

    # remove (
    coordinate_list=${coordinate_list//"("/}

    # remove )
    coordinate_list=${coordinate_list//")"/}

    coordinates=()
    coordinates+="[["

    # get a list of all coordinates (separated by comma)
    while IFS=',' read -ra coo; do
        for i in "${coo[@]}"; do
            # get lon & lat 
            lon_lat=($i)
            # fix subcoordinates + operator concatenate not exist
            subcoordinates="[${lon_lat[0]},${lon_lat[1]}]"
            coordinates+="${subcoordinates},"
        done
    done <<< "$coordinate_list"

    # remove last comma
    coordinates=${coordinates%?}

    coordinates+="]]"

    geom_detail="{\"type\": \"Polygon\", \"coordinates\": $coordinates}"

    # no coverages yet, so we insert
    if [ "$numberOfCoverage" = "0" ]; then
        echo "inserting coverages"
        # Build JSON payload
        payload=$(jq -n \
            --arg coverage_type "$coverage_type" \
            --arg geom_detail "$geom_detail" \
            '{
                coverage_type: $coverage_type,
                geometry: {
                    geom: null,
                    geom_detail: $geom_detail
                }
            }')

        # Send the POST request to create a coverage in DB
        responses+=$(curl -X POST -v -H "Content-Type: application/json" -H "Authorization: JWT token=\"$JWTToken\"" -d "$payload" "$COVERAGE_API_URL")
    fi
done

# Log final progress
echo "Completed. Total Navitia API requests: $NAVITIA_REQUEST_COUNT" >> $LOG_FILE

echo "Stop time :" >> $LOG_FILE
echo $(date +"%Y-%m-%d-%H-%M-%S") >> $LOG_FILE