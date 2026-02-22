import logging
import pprint

# Import the Singleton provider we defined in the previous step
# (Assumes the file was named opex_provider.py)
from utils.models.opex_provider import OpexHybridProvider

logger = logging.getLogger(__name__)

# Create the global Singleton instance
# Other files will import this variable directly: "from database import OpexDB"
OpexDB = OpexHybridProvider()

# If you had a Vector DB provider, you would instantiate it here too:
# VectorDB = VectorStoreProvider()


# ---------------------------------------------------------------------------
# pgvector health check — cached so it only runs once per process
# ---------------------------------------------------------------------------
_opex_db_status = None  # None = not checked, True = ok, str = error message


def check_opex_db() -> tuple:
    """
    Check whether the opex_data_hybrid table is queryable.
    Returns (ok: bool, error_message: str | None).
    Result is cached for the lifetime of the process.
    """
    global _opex_db_status
    if _opex_db_status is not None:
        if _opex_db_status is True:
            return True, None
        return False, _opex_db_status

    try:
        from sqlalchemy import text
        with OpexDB.engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM opex_data_hybrid LIMIT 1"))
        _opex_db_status = True
        return True, None
    except Exception as e:
        err_str = str(e)
        if "vector" in err_str.lower() and ("libdir" in err_str.lower() or "no such file" in err_str.lower()):
            msg = (
                "The **pgvector** extension is not installed on your PostgreSQL server. "
                "Install it (`sudo dnf install pgvector_15` on RHEL, `brew install pgvector` on macOS) "
                "then restart PostgreSQL and run `CREATE EXTENSION IF NOT EXISTS vector;` in your database. "
                "See the README for detailed instructions."
            )
        elif "does not exist" in err_str.lower() or "undefined_table" in err_str.lower():
            msg = (
                "The `opex_data_hybrid` table does not exist. "
                "Run `python bootstrap_db.py` to initialize the database schema."
            )
        else:
            msg = f"Database connection error: {err_str[:200]}"
        _opex_db_status = msg
        logger.warning(f"OpEx DB check failed: {msg}")
        return False, msg

if __name__ == "__main__":
    """
    Test block to verify connectivity and basic queries.
    Run this file directly: python database.py
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    print("--- Testing Opex Hybrid Database Connection ---")

    # 1. Test: Get Unique Project Numbers
    try:
        projects = OpexDB.get_unique_project_numbers()
        print(f"\n[+] Found {len(projects)} unique projects.")
        print(f"    Sample: {projects[:5]}")
    except Exception as e:
        print(f"[-] Error fetching projects: {e}")

    # 2. Test: Get Records by Fiscal Year
    # (Adjust 'FY24' to a value likely to exist in your data)
    test_fy = "FY24"
    try:
        records = OpexDB.get_projects_by_fiscal_year(test_fy)
        print(f"\n[+] Found {len(records)} records for {test_fy}.")
        if records:
            print("    First Record Sample:")
            # Use pprint to show the object dict, excluding internal SQLAlchemy state
            sample_data = {k: v for k, v in records[0].__dict__.items() if not k.startswith('_')}
            pprint.pprint(sample_data)
    except Exception as e:
        print(f"[-] Error fetching records for {test_fy}: {e}")

    # 3. Test: Hybrid Search Helper (Mock UUID)
    # This tests the query structure even if the UUID doesn't exist
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    try:
        record = OpexDB.get_record_by_uuid(fake_uuid)
        if record:
            print(f"\n[+] Found record for UUID {fake_uuid}")
        else:
            print(f"\n[+] Correctly returned None for non-existent UUID {fake_uuid}")
    except Exception as e:
        print(f"[-] Error executing UUID search: {e}")