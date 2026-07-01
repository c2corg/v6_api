# Documentation for "Mobilité douce" made by Smart/Origin

This documentation concerns the **"Public Transport Access"** box code, which appears on the camp to camp routes

⚠️ S/O added a .env to the backend. 

```sh
v6_api/.env.template #rename it into .env
```

Variables defined in the above file must be available at runtime for the scripts to execute correctly.
One can either source the env file, or update the compose configuration to include them in the api container runtime (this is the production approach).

If you haven't already, update the database with Alembic (this will create the missing tables and fields) :
```bash
docker-compose exec api .build/venv/bin/alembic upgrade head
```

## "Show Nearby Stops" section

This section is used to search for public transport stops around 'access' waypoints.
The public transport data comes from an external API called Navitia, which is stored in the CamptoCamp database.

**IF YOU DON'T HAVE ANY RESULT ON THE "Public Transports Access" section** : this means that your imported database does not contain Navitia data.
To populate it, run one of the two scripts in `scripts/`:

| Script | When to use |
|--------|-------------|
| `scripts/public_transport/get_public_transports.sh [region]` | Run **from the host** (outside containers) — uses `podman-compose`/`docker-compose` to reach the database |
| `scripts/public_transport/get_public_transports.bm.sh [region]` | Run **from within a container** or any machine with direct database access — uses `psql` directly |

The `[region]` argument is optional (default: `france`). Valid values:

| Value | Coverage | Approximate duration |
|-------|----------|----------------------|
| `france` | All of France | ~3h |
| `isere` | Isère department only | ~18 min (useful for local dev) |
| `rhone` | Rhône department only | ~15 min |

**Required environment variables** (set before running the script):

```sh
NAVITIA_API_KEY=...                    # Navitia API key
MAX_DISTANCE_WAYPOINT_TO_STOPAREA=5000 # Max distance in meters
WALKING_SPEED=1.12                     # Walking speed in m/s
MAX_STOP_AREA_FOR_1_WAYPOINT=5         # Max stop areas per waypoint
```

**Examples:**

Production (from within the container, full France):
```sh
sh scripts/public_transport/get_public_transports.bm.sh france
```

Local dev (from the host, Isère only):
```sh
sh scripts/public_transport/get_public_transports.sh isere
```

### Files created / used for this section :

FRONT-END :

`c2c_ui/src/views/document/utils/boxes/TransportsBox.vue` => Parent view of the section


`c2c_ui/src/views/document/RouteView.vue`=> View that call TransportsBox and IsReachableByPublicTransportsBox

`c2c_ui/src/views/document/utils/boxes/NearbyStopsSection.vue` => Features for nearby stops

`c2c_ui/src/views/document/utils/boxes/IsReachableByPublicTransportsBox.vue`=> Displays the small card on the left to indicate if there is at least one transport uploaded by the database for this route

`c2c_ui/src/components/map/OlMap.vue` => Map-related features

`c2c_ui/src/components/map/map-utils.vue` => Map Objects Style

`c2c_ui/src/js/apis/transport-service.js` => Calls the backend to get results from the database

`c2c_ui/src/assets/img/boxes/...` => Images

<br/>
BACK-END :

`v6_api/c2corg_api/models/waypoint_stoparea.py` => waypoint_stoparea class

`v6_api/c2corg_api/models/stoparea.py` => stoparea class

`v6_api/c2corg_api/views/waypoint_stoparea.py` => waypoint_stoparea endpoints

`v6_api/c2corg_api/views/stoparea.py` => stoparea waypoints

`v6_api/c2corg_api/__init__.py` => add a event : after each access waypoint created on C2C, the nearby stops are requested

`v6_api/alembic_migration/versions/bb61456d557f_create_stops_and_waypoints_stops.py`=> Creates the stops and waypoints_stops tables

`v6_api/c2corg_api/__init__.py`=> sqlalchemy event (it's like db trigger) : after each access waypoint insert, we request Navitia


## "Plan a trip" section

This section is used to plan a trip by calling the Navitia API.
Unlike the previous section, we don't store the results in the database; we query Navitia directly by launching a query from the backend.
This section uses the calculated_duration attribute, **which is calculated with the `calcul_duration_for_routes.bm.sh` script in the backend (see backend documentation)**

Note that the `calcul_duration_for_routes.bm.sh` is intended to run from within the container. A variant named `calcul_duration_for_routes.sh` can be used to launch the script from the host.

If you need to update the calculated duration of itineraries, you can run this :

1) Go on `v6_api/c2corg_api/views/document.py` and put the LIMIT_MAX to 100000 :
```python
# the maximum number of documents that can be returned in a request
LIMIT_MAX = 100000
```


2) Run the script
```
(on api_v6/ )
sh calcul_duration_for_routes.bm.sh
```
3) Put the limit back to 100
```python
# the maximum number of documents that can be returned in a request
LIMIT_MAX = 100
```

Files created / used :

FRONT-END :

`c2c_ui/src/views/document/utils/boxes/TransportsBox.vue` => Parent view of the section

`c2c_ui/src/views/document/utils/boxes/PlanATripSection.vue` => Features for planning a trip

`c2c_ui/src/js/apis/navitia-service.js` => Navitia's call on the back

`c2c_ui/src/components/map/OlMap.vue` => Map-related features

`c2c_ui/src/components/map/map-utils.vue` => Map Objects Style

`c2c_ui/src/assets/img/boxes/... (images)` => Images

<br/>
BACK-END :

`v6_api/c2corg_api/views/navitia.py` => Call Navitia API

`v6_api/c2corg_api/__init__.py` => add a event : after each route created on C2C, the calculated_duration is calculed

`v6_api/alembic_migration/versions/6b40cb9c7c3d_add_calculated_duration_to_routes.py` => Add calculated_duration in DB, on routes objects

`v6_api/c2corg_api/__init__.py`=> sqlalchemy event (it's like db trigger) : after each route insert, we calculate the duration


## Lot 3 - Itinévert



****FRONT-END****

`c2c_ui/src/components/itinevert/*` : 
- **ItinevertBanner.vue** => The banner of the Itinevert tool
- **ItinevertFilterView.vue** => The view displayed when too much routes are found when searching for routes in a mountain range
- **ItinevertLoadingView.vue** => The view displayed when loading is needed in Itinévert (mostly isochrone/journey queries)
- **ItinevertNoResultView.vue** => The view displayed when no results were found. Errors from API can also be seen in this view.
- **ItinevertPageSelector.vue** => The pagination widget used for Itinévert since we can't rely on existing one (that is based on URL only)
- **ItinevertResultView.vue** => Similar to DocumentsView, display the results on the map
- **ItinevertWizard.vue** => The form for Itinévert, as well as the logic that orchestrate view display

`c2c_ui/src/components/generic/inputs` : 
- **InputRadioButton.vue** => Input for radio buttons
- **InputAddress.vue** => Input for address, supports geolocation from browser as well as loading user address from its profile. Uses photon API.
- **InputAutocomplete.vue** => Autocomplete input

`c2c_ui/src/views/portal` : 
- **ItinevertView.vue** : The root component for Itinévert

`c2c_ui/src/assets/img/itinevert/banner-img/*` :
- any images here will be shown randomly as a banner in Itinévert tool

`c2c_ui/src/js/apis` : 
- **itinevert-service.js** : The service for Itinévert dedicated route calls
- **navitia-service.js** : The service for Navitia API calls

****BACK-END****

`v6_api/c2corg_api/views/navitia.py` :
- calls to Navitia API (**isochrone**, **journey with coverage**), **job handling** for journey queries

`v6_api/c2corg_api/views/route.py` :
- add **/reachableroute** route to get routes that have an access waypoint that is associated to a waypoint stop area

`v6_api/c2corg_api/views/waypoint.py` :
- add **/reachablewaypoints** route to get access waypoints that are associated to a waypoint stop area

`v6_api/c2corg_api/views/coverage.py` : 
- routes for coverages

`v6_api/c2corg_api/models/coverage.py` : 
- model for coverages

`v6_api/alembic_migration/versions/27bf1b7197a6_add_coverages.py`:
- create **Coverage** table in database

***
Script `update_navitia_coverage.sh` :

**When to run** 

Everytime Navitia updates its coverage for France.

**Where to run**

The script can be launched from any machine with access to the API, including the API docker container itself in production.

**What does it do**

- Delete all coverages from C2C database (if any)
- Get all coverages for France from navitia /coverages API
- Insert all coverages for France in C2C database

The coverages are stored in Coverage table.

**Purpose of this script**

Coverages are stored in database so that we don't have to call Navitia API every time we want to get coverage.

Finding the coverage is mandatory for **/isochrone** Navitia calls, and give better results for **/journey** Navitia calls

**Parameters**

- Username ex: 'user123'  
- Password ex: 'password123' (make sure to escape special characters) 
- Base API URL ex: 'http://localhost' 
- API Port ex: '6543' 

**Who can run it**

Any moderators, since deleting documents via API can only be done by moderators.

**Volumetry**

There are only five coverages for France :
- fr-se
- fr-ne
- fr-sw
- fr-nw
- fr-idf