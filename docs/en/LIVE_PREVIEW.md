# Live preview

While Claude builds a model, your open Blender shows it step by step: each part and detail appears as it is added,
growing up from the base. The heavy work (geometry, checks, renders) runs in a separate background Blender; the open
one only displays the result.

```
Claude -> connector -> perakit bangun (background)
                         | after each part/detail: langkah_NN.npz + tonton.json (written atomically)
                         v
                 <workspace>/artefak/tonton/<project>/   <- watched by the add-on every 0.35 s
                         v
        your Blender: object "TONTON" replaced each step; the last step is model.glb
```

- No network socket: the add-on only reads files.
- The last step is the exact mesh that was saved, not an approximation.
- Steps play one at a time even if the background build already finished.
- A newer job folder takes over automatically.

## Using it

After **Install & connect to Claude** the preview starts automatically whenever Blender opens (only new jobs;
**Start live preview** replays the latest one). Every `perakit bangun` started from Claude records steps.

## Limits

- Each step is a full mesh (about 6 MB for a 61 mm chess knight at 0.2 mm voxels). The folder is overwritten per
  project.
- Only the `perakit` module records steps so far.
