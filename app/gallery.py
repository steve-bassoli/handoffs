"""Gallery: pictures the agents made, from image proofs already attached to tasks (Steve, 2026-10-19:
"I want to see bot creativity in our house"). Read only; it lists what is attached and never copies the bytes."""
import json

IMAGE_TYPES = ('image/png', 'image/jpeg')


def gallery(service, limit=60):
    sql = """SELECT e.task_id, t.title, e.created_at,
                    json_extract(e.data, '$.proof_id'), json_extract(e.data, '$.filename'),
                    json_extract(e.data, '$.media_type'), json_extract(e.data, '$.description')
             FROM events e JOIN tasks t ON t.id = e.task_id
             WHERE e.kind = 'proof_attached' AND json_extract(e.data, '$.media_type') IN (?, ?)
             ORDER BY e.seq DESC LIMIT ?"""
    with service.db.engine.connect() as c:
        rows = c.exec_driver_sql(sql, (*IMAGE_TYPES, limit)).fetchall()
    items = []
    for task_id, title, created, proof_id, filename, media_type, description in rows:
        if not (isinstance(proof_id, str) and isinstance(filename, str)):
            continue
        items.append({'task_id': task_id, 'task_title': title, 'created_at': created, 'proof_id': proof_id,
                      'filename': filename, 'media_type': media_type,
                      'description': description[:600] if isinstance(description, str) else '',
                      'download_url': f'/api/v1/tasks/{task_id}/proofs/{proof_id}'})
    return {'items': items}

