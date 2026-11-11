import hashlib
import json

from app.core.exceptions import fail
from bonus.models import OfflineReceipt
from mandatory.services import music_service as music


def sync_offline(db, resource_id, user, data):
    # The route locks the user's subscription first, then this resource. Retrying
    # a lost response returns the original result without applying the edit twice.
    resource = music.load(db, "playlist", resource_id, user, True)
    music.editable(db, resource, user)
    payload = json.dumps(
        {"resource_id": str(resource_id), **data.model_dump(mode="json")}, sort_keys=True
    )
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    receipt = db.get(OfflineReceipt, (user.id, data.mutation_id))
    if receipt:
        if receipt.payload_digest != fingerprint:
            fail(409, "mutation_conflict", "Mutation ID was already used for a different edit")
        return receipt.result
    music.version(resource, data.base_version)
    tracks = {t["id"]: t for t in resource.tracks}
    ids = [str(value) for value in data.track_ids]
    if any(value not in tracks for value in ids):
        fail(422, "invalid_track", "Offline edits may only reorder or remove existing tracks")
    resource.tracks = [tracks[value] for value in ids]
    resource.version += 1
    db.flush()
    result = music.view(db, resource, user)
    result = json.loads(json.dumps(result, default=str))
    db.add(
        OfflineReceipt(
            user_id=user.id,
            mutation_id=data.mutation_id,
            resource_id=resource_id,
            payload_digest=fingerprint,
            result=result,
        )
    )
    return result
