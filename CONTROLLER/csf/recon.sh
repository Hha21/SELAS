#!/bin/bash
# Read-only survey of what CSF3 already provides. Changes nothing; safe to rerun.
# Run on a login node:  ssh csf3 'bash -s' < recon.sh
echo "=========== identity / host ==========="
hostname; whoami; date -u

echo; echo "=========== storage & quota ==========="
for d in "$HOME" "$HOME/scratch" "$HOME/h200-scratch" /mnt/h200-scratch/$USER; do
    [ -e "$d" ] && printf '%-34s %s\n' "$d" "$(df -h "$d" 2>/dev/null | awk 'NR==2{print $2" total, "$4" avail"}')"
done
command -v quota >/dev/null && quota -s 2>/dev/null | head -5

echo; echo "=========== container runtimes ==========="
for c in apptainer singularity podman docker; do
    printf '%-12s ' "$c"; command -v $c >/dev/null && $c --version 2>&1 | head -1 || echo "absent"
done
module avail 2>&1 | grep -iE 'apptainer|singular|podman' | head -5 || true

echo; echo "=========== cuda / python modules ==========="
module avail -L 2>&1 | grep -iE 'libs/cuda|apps/binapps/anaconda|apps/python|tools/env' | head -20

echo; echo "=========== python / venvs present ==========="
python3 --version 2>&1
for v in "$HOME"/*/.venv "$HOME"/.venv "$HOME"/scratch/*/.venv "$HOME"/h200-scratch/*/.venv; do
    [ -x "$v/bin/python" ] && printf '%-48s ' "$v" && "$v/bin/python" -c \
      'import importlib.util as u,sys;print("py",".".join(map(str,sys.version_info[:3])),
      "torch" if u.find_spec("torch") else "-", "vllm" if u.find_spec("vllm") else "-",
      "transformers" if u.find_spec("transformers") else "-")' 2>/dev/null || true
done

echo; echo "=========== huggingface cache & token ==========="
echo "HF_HOME=${HF_HOME:-<unset>}  HF_TOKEN=${HF_TOKEN:+<set>}${HF_TOKEN:-<unset>}"
for h in "$HOME/.cache/huggingface" "$HOME/scratch/hf" "$HOME/h200-scratch/hf" "$HOME/h200-scratch/models"; do
    [ -d "$h" ] && echo "--- $h ($(du -sh "$h" 2>/dev/null | cut -f1))" && \
      ls "$h/hub" 2>/dev/null | head -10
done
[ -f "$HOME/.cache/huggingface/token" ] && echo "HF token file: present" || echo "HF token file: absent"

echo; echo "=========== any 70B / gemma weights already here ==========="
find "$HOME" -maxdepth 6 \( -iname '*Llama-3.3-70B*' -o -iname '*gemma-3-27b*' -o -iname '*Qwen2.5-7B*' \) \
     -not -path '*/.git/*' 2>/dev/null | head -10 || echo "(none found)"

echo; echo "=========== slurm: our access ==========="
sacctmgr -nP show assoc user=$USER format=Account,Partition,QOS 2>/dev/null | head -20
echo "--- gpuH partitions ---"
sinfo -p gpuH,gpuH_short -o '%P %a %l %D %t %N %G' 2>/dev/null | head
echo "--- our queue ---"
squeue --me 2>/dev/null | head

echo; echo "=========== outbound network from login node ==========="
for hp in huggingface.co:443 github.com:443; do
    timeout 6 bash -c "cat </dev/null >/dev/tcp/${hp/:/\/}" 2>/dev/null \
      && echo "$hp reachable" || echo "$hp BLOCKED"
done
echo "=========== end ==========="
