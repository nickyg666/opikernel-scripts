#!/usr/bin/env python3
"""Instrument pvr_job.c EINVAL sites with distinct PVRDBG labels (J*)."""
import re

F = "/home/host/kernel-trees/host-build/mainline-6.18/drivers/gpu/drm/imagination/pvr_job.c"
src = open(F).read()

edits = [
    # create_job: stream checks
    ('\tif (!args->cmd_stream || !args->cmd_stream_len)\n\t\treturn ERR_PTR(-EINVAL);',
     '\tif (!args->cmd_stream || !args->cmd_stream_len) {\n\t\tprintk("PVRDBG J1 stream=0x%llx len=%u\\n", (u64)args->cmd_stream, args->cmd_stream_len);\n\t\treturn ERR_PTR(-EINVAL);\n\t}'),
    # ctx lookup
    ('\tjob->ctx = pvr_context_lookup(pvr_file, args->context_handle);\n\tif (!job->ctx) {\n\t\terr = -EINVAL;',
     '\tjob->ctx = pvr_context_lookup(pvr_file, args->context_handle);\n\tif (!job->ctx) {\n\t\tprintk("PVRDBG J2 ctx_handle=%u not found\\n", args->context_handle);\n\t\terr = -EINVAL;'),
    # hwrt lookup
    ('\t\tif (!job->hwrt) {\n\t\t\terr = -EINVAL;\n\t\t\tgoto err_put_job;\n\t\t}',
     '\t\tif (!job->hwrt) {\n\t\t\tprintk("PVRDBG J3 hwrt set=%u idx=%u not found\\n", args->hwrt.set_handle, args->hwrt.data_index);\n\t\t\terr = -EINVAL;\n\t\t\tgoto err_put_job;\n\t\t}'),
    # geom: flags mask
    ('\tif (args->flags & ~DRM_PVR_SUBMIT_JOB_GEOM_CMD_FLAGS_MASK)\n\t\treturn -EINVAL;',
     '\tif (args->flags & ~DRM_PVR_SUBMIT_JOB_GEOM_CMD_FLAGS_MASK) {\n\t\tprintk("PVRDBG J4 geom flags=0x%x\\n", args->flags);\n\t\treturn -EINVAL;\n\t}'),
    # geom: ctx type
    ('\tif (job->ctx->type != DRM_PVR_CTX_TYPE_RENDER)\n\t\treturn -EINVAL;\n\n\tif (!job->hwrt)\n\t\treturn -EINVAL;\n\n\tjob->fw_ccb_cmd_type = ROGUE_FWIF_CCB_CMD_TYPE_GEOM;',
     '\tif (job->ctx->type != DRM_PVR_CTX_TYPE_RENDER) {\n\t\tprintk("PVRDBG J5 geom ctx_type=%d\\n", job->ctx->type);\n\t\treturn -EINVAL;\n\t}\n\n\tif (!job->hwrt) {\n\t\tprintk("PVRDBG J6 geom hwrt NULL\\n");\n\t\treturn -EINVAL;\n\t}\n\n\tjob->fw_ccb_cmd_type = ROGUE_FWIF_CCB_CMD_TYPE_GEOM;'),
    # frag: flags mask
    ('\tif (args->flags & ~DRM_PVR_SUBMIT_JOB_FRAG_CMD_FLAGS_MASK)\n\t\treturn -EINVAL;',
     '\tif (args->flags & ~DRM_PVR_SUBMIT_JOB_FRAG_CMD_FLAGS_MASK) {\n\t\tprintk("PVRDBG J7 frag flags=0x%x\\n", args->flags);\n\t\treturn -EINVAL;\n\t}'),
    # frag: ctx type + hwrt
    ('\tif (job->ctx->type != DRM_PVR_CTX_TYPE_RENDER)\n\t\treturn -EINVAL;\n\n\tif (!job->hwrt)\n\t\treturn -EINVAL;\n\n\tjob->fw_ccb_cmd_type = (args->flags & DRM_PVR_SUBMIT_JOB_FRAG_CMD_PARTIAL_RENDER) ?',
     '\tif (job->ctx->type != DRM_PVR_CTX_TYPE_RENDER) {\n\t\tprintk("PVRDBG J8 frag ctx_type=%d\\n", job->ctx->type);\n\t\treturn -EINVAL;\n\t}\n\n\tif (!job->hwrt) {\n\t\tprintk("PVRDBG J9 frag hwrt NULL\\n");\n\t\treturn -EINVAL;\n\t}\n\n\tjob->fw_ccb_cmd_type = (args->flags & DRM_PVR_SUBMIT_JOB_FRAG_CMD_PARTIAL_RENDER) ?'),
]

n = 0
for old, new in edits:
    if old in src:
        src = src.replace(old, new, 1)
        n += 1
    else:
        print(f"MISS: {old[:60]!r}")

# also log fw_cmd_init err inside geom/frag
src = src.replace(
    "\terr = pvr_fw_cmd_init(job->pvr_dev, job, &pvr_cmd_geom_stream,\n\t\t\t      args->cmd_stream, args->cmd_stream_len);\n\tif (err)\n\t\treturn err;",
    "\terr = pvr_fw_cmd_init(job->pvr_dev, job, &pvr_cmd_geom_stream,\n\t\t\t      args->cmd_stream, args->cmd_stream_len);\n\tif (err) {\n\t\tprintk(\"PVRDBG J10 geom fw_cmd_init err=%d len=%u\\n\", err, args->cmd_stream_len);\n\t\treturn err;\n\t}", 1)
src = src.replace(
    "\terr = pvr_fw_cmd_init(job->pvr_dev, job, &pvr_cmd_frag_stream,\n\t\t\t      args->cmd_stream, args->cmd_stream_len);\n\tif (err)\n\t\treturn err;",
    "\terr = pvr_fw_cmd_init(job->pvr_dev, job, &pvr_cmd_frag_stream,\n\t\t\t      args->cmd_stream, args->cmd_stream_len);\n\tif (err) {\n\t\tprintk(\"PVRDBG J11 frag fw_cmd_init err=%d len=%u\\n\", err, args->cmd_stream_len);\n\t\treturn err;\n\t}", 1)

if "linux/printk" not in src and "#include <linux" in src:
    src = src.replace("#include <linux", "#include <linux/printk.h>\n#include <linux", 1)

open(F, "w").write(src)
print(f"applied {n}/7 structural edits + fw_cmd_init logs")
