from kb.storage import connect

with connect() as c:
    docs = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    quarantined = c.execute("SELECT COUNT(*) FROM documents WHERE status='quarantined'").fetchone()[0]

print(f"docs: {docs}")
print(f"chunks: {chunks}")
print(f"quarantined: {quarantined}")

# Also show each doc
print("\nDocuments:")
with connect() as c:
    for row in c.execute("SELECT path, version, status FROM documents ORDER BY path"):
        print(f"  {row['path']}  v{row['version']}  [{row['status']}]")