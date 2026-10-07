from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION moderation_adminaction_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'moderation_adminaction is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER moderation_adminaction_no_update_delete
    BEFORE UPDATE OR DELETE ON moderation_adminaction
    FOR EACH ROW EXECUTE FUNCTION moderation_adminaction_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS moderation_adminaction_no_update_delete ON moderation_adminaction;
DROP FUNCTION IF EXISTS moderation_adminaction_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("moderation", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
