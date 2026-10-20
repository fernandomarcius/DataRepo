"""
View Service - Handles smart view updates with dependency management.
Provides functions to detect dependent views, save DDLs to history, and perform cascade updates.
"""
from db import execute_query, engine, LOCAL_SCHEMA
from kit.identifiers import validate_data_object_name as _validate_data_object_name
from sqlalchemy import text

# -------------------------------------
# Audit Table Initialization
# -------------------------------------


# -------------------------------------
# Dependency Detection
# -------------------------------------

def get_dependent_views(view_name):
    """
    Returns a list of view names that depend on the given view.
    Uses PostgreSQL system catalogs to find dependencies.
    """
    query = f"""
        SELECT DISTINCT dependent.relname AS dependent_view
        FROM pg_depend d
        JOIN pg_rewrite r ON d.objid = r.oid
        JOIN pg_class dependent ON r.ev_class = dependent.oid
        JOIN pg_class source ON d.refobjid = source.oid
        JOIN pg_namespace ns ON dependent.relnamespace = ns.oid
        WHERE source.relname = :view_name
          AND source.relkind = 'v'
          AND dependent.relkind = 'v'
          AND dependent.relname != :view_name
          AND ns.nspname = '{LOCAL_SCHEMA}'
    """
    result = execute_query(query, {"view_name": view_name})
    return [row['dependent_view'] for row in result] if result else []


def get_all_dependent_views_recursive(view_name, visited=None):
    """
    Recursively finds all views that depend on the given view.
    Returns a list in dependency order (leaf views first).
    """
    if visited is None:
        visited = set()

    if view_name in visited:
        return []

    visited.add(view_name)
    direct_dependents = get_dependent_views(view_name)
    all_dependents = []

    for dep in direct_dependents:
        # Get dependents of this dependent (recursive)
        sub_deps = get_all_dependent_views_recursive(dep, visited)
        all_dependents.extend(sub_deps)
        all_dependents.append(dep)

    return all_dependents


# -------------------------------------
# View Definition Retrieval
# -------------------------------------

def get_view_definition(view_name):
    """
    Returns the SQL definition of a view using pg_get_viewdef.
    """
    query = """
        SELECT pg_get_viewdef(:view_name, true) AS definition
    """
    result = execute_query(query, {"view_name": view_name})
    if result and len(result) > 0:
        return result[0]['definition']
    return None


def view_exists(view_name):
    """Checks if a view exists in the public schema."""
    query = f"""
        SELECT COUNT(*) as count
        FROM information_schema.views
        WHERE table_schema = '{LOCAL_SCHEMA}' AND table_name = :view_name
    """
    result = execute_query(query, {"view_name": view_name})
    return result and result[0]['count'] > 0


# -------------------------------------
# Audit Functions
# -------------------------------------

def save_view_to_history(view_name, definition, operation, related_to=None):
    """
    Saves a view's definition to the _view_history table.
    """
    query = """
        INSERT INTO _view_history (view_name, view_definition, operation, related_to)
        VALUES (:view_name, :definition, :operation, :related_to)
    """
    with engine.connect() as conn:
        conn.execute(text(query), {
            "view_name": view_name,
            "definition": definition,
            "operation": operation,
            "related_to": related_to
        })
        conn.commit()
    print(f"DEBUG: Saved {view_name} to _view_history (operation: {operation})", flush=True)


# -------------------------------------
# Smart View Update
# -------------------------------------

def replace_view_reference(sql_definition, old_name, new_name):
    """
    Replaces references to old_name with new_name in an SQL definition.
    Uses word boundary matching to avoid partial replacements.
    """
    import re
    # Match the view name as a whole word (case-insensitive)
    pattern = r'\b' + re.escape(old_name) + r'\b'
    return re.sub(pattern, new_name, sql_definition, flags=re.IGNORECASE)


def smart_update_view(view_name, new_definition, new_name=None):
    """
    Updates a view, handling dependencies automatically.
    Optionally renames the view if new_name is provided.

    1. If no dependents and no rename, try CREATE OR REPLACE VIEW.
    2. If dependents exist or renaming:
       - Save all dependent view definitions to history
       - Drop target view with CASCADE
       - Create view with new definition (and new name if provided)
       - Recreate dependents with updated references (if renamed)

    Returns: dict with 'success', 'message', and optionally 'recreated_views' or 'error'
    """
    print(f"DEBUG: smart_update_view called for {view_name}", flush=True)
    if new_name:
        print(f"DEBUG: Renaming to {new_name}", flush=True)

    # DDL nao aceita parametro vinculado para identificador, entao o nome entra
    # por interpolacao. Validar aqui e o que impede injecao: `new_name` vem do
    # corpo da requisicao e ia direto para `CREATE VIEW {final_name} AS ...`,
    # sem passar sequer pelo view_exists que protege o alvo.
    try:
        _validate_data_object_name(view_name)
        if new_name:
            _validate_data_object_name(new_name)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Determine the final view name
    final_name = new_name if new_name else view_name
    is_renaming = new_name and new_name != view_name

    # Check if view exists
    if not view_exists(view_name):
        return {
            "success": False,
            "error": f"View '{view_name}' does not exist"
        }

    # Check if new name already exists (if renaming)
    if is_renaming and view_exists(new_name):
        return {
            "success": False,
            "error": f"Cannot rename: view '{new_name}' already exists"
        }

    # Get all dependent views (recursively, in dependency order)
    dependents = get_all_dependent_views_recursive(view_name)
    print(f"DEBUG: Found {len(dependents)} dependent views: {dependents}", flush=True)

    # Fetch old definition before any mutation (for audit)
    old_definition = get_view_definition(view_name)

    # If no dependents and not renaming, try simple CREATE OR REPLACE
    if not dependents and not is_renaming:
        try:
            query = f"CREATE OR REPLACE VIEW {view_name} AS {new_definition}"
            with engine.connect() as conn:
                # nosemgrep: avoid-sqlalchemy-text -- DDL nao aceita bind de identificador; nome validado acima
                conn.execute(text(query))
                conn.commit()
            return {
                "success": True,
                "message": f"View '{view_name}' updated successfully (no dependencies)",
                "had_dependencies": False,
                "renamed": False,
                "old_definition": old_definition,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to update view: {str(e)}"
            }

    # Has dependents or is renaming - need to save, drop cascade, and recreate
    saved_definitions = {}

    try:
        # 1. Save all dependent view definitions (in reverse order for later recreation)
        for dep_view in dependents:
            definition = get_view_definition(dep_view)
            if definition:
                saved_definitions[dep_view] = definition
                save_view_to_history(dep_view, definition, 'DROPPED_FOR_UPDATE', view_name)

        # Also save the target view itself
        target_definition = get_view_definition(view_name)
        if target_definition:
            operation = 'RENAMED' if is_renaming else 'UPDATED'
            save_view_to_history(view_name, target_definition, operation, new_name if is_renaming else None)

        # 2. Drop the target view with CASCADE (this drops all dependents)
        drop_query = f"DROP VIEW IF EXISTS {view_name} CASCADE"
        with engine.connect() as conn:
            # nosemgrep: avoid-sqlalchemy-text -- DDL nao aceita bind de identificador; nome validado acima
            conn.execute(text(drop_query))
            conn.commit()
        print(f"DEBUG: Dropped {view_name} with CASCADE", flush=True)

        # 3. Create the view with the new definition (and new name if renaming)
        create_query = f"CREATE VIEW {final_name} AS {new_definition}"
        with engine.connect() as conn:
            # nosemgrep: avoid-sqlalchemy-text -- DDL nao aceita bind de identificador; nome validado acima
            conn.execute(text(create_query))
            conn.commit()
        print(f"DEBUG: Created {final_name} with new definition", flush=True)

        # 4. Recreate dependent views
        # If renaming, update their definitions to reference the new name
        recreated = []
        for dep_view in dependents:
            if dep_view in saved_definitions:
                dep_definition = saved_definitions[dep_view]

                # If renaming, replace references to old name with new name
                if is_renaming:
                    dep_definition = replace_view_reference(dep_definition, view_name, final_name)

                recreate_query = f"CREATE VIEW {dep_view} AS {dep_definition}"
                with engine.connect() as conn:
                    # nosemgrep: avoid-sqlalchemy-text -- DDL nao aceita bind de identificador; nome validado acima
                    conn.execute(text(recreate_query))
                    conn.commit()
                recreated.append(dep_view)
                print(f"DEBUG: Recreated dependent view {dep_view}", flush=True)

        message = f"View '{view_name}'"
        if is_renaming:
            message += f" renamed to '{final_name}'"
        else:
            message += " updated"
        message += f" successfully with {len(recreated)} dependent views recreated"

        return {
            "success": True,
            "message": message,
            "had_dependencies": len(dependents) > 0,
            "renamed": is_renaming,
            "new_name": final_name if is_renaming else None,
            "recreated_views": recreated,
            "old_definition": old_definition,
        }

    except Exception as e:
        print(f"DEBUG: Error during smart_update_view: {str(e)}", flush=True)
        return {
            "success": False,
            "error": f"Failed to update view: {str(e)}",
            "saved_to_history": list(saved_definitions.keys())
        }
