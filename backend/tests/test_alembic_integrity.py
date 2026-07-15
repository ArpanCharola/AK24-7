from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"


def test_alembic_revision_graph_is_resolvable():
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert heads, "expected at least one alembic head"

    revisions = list(script.walk_revisions(base="base", head="heads"))
    assert revisions, "expected alembic to load at least one revision"

    revision_ids = {rev.revision for rev in revisions}
    for rev in revisions:
        down_revisions = rev._all_down_revisions or ()
        for parent in down_revisions:
            assert parent in revision_ids, (
                f"Revision {rev.revision} points to missing parent {parent}. "
                "Use the actual Alembic revision id, not the migration filename."
            )

    assert heads == ["0019_production_reconcile"]
