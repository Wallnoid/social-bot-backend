"""
Move the test database between migrations, to test the data steps against the state they ran in.
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def migrate_to(*targets):
    """Migrate to these migrations (all the latest ones if none) and return the models there."""
    executor = MigrationExecutor(connection)
    targets = list(targets) or executor.loader.graph.leaf_nodes()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps
