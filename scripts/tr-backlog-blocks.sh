#!/bin/bash
# authoritative per-block integrity assert
cd /home/host/opikernel || exit 1
awk '/^### BL-/{h=$2} /^status:/{c[h]++} /^claimed-by:/{p[h]++}
     END{anom=0; for(k in c) if(c[k]!=1){print "BAD status "k" x"c[k]; anom++}
         for(k in p) if(p[k]!=1){print "BAD claimed-by "k" x"p[k]; anom++}
         print "blocks="length(c)" anomalies="anom}' agentic-pool/BACKLOG.md
grep -o '^### BL-[0-9]*' agentic-pool/BACKLOG.md | tr '\n' ' '; echo
