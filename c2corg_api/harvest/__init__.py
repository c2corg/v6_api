"""Harvesting: data of other services fetched in the background, and stored.

The scheduler (scripts/jobs/scheduler.py) runs harvest_tick every minute: it
fetches the sources whose time has come, each harvester saying when to come
back (policy). The users then read the database, never wait for a service.
"""
