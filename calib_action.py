#!/usr/bin/env python3
"""US-East calibration: boundary-aligned tip-fire via bloXroute from GitHub Actions (US runner).
Measures the TRUE US→bloXroute→leader landing offset."""
import os, json, base64, requests, time, sys
from datetime import datetime, timezone
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.hash import Hash

S = requests.Session(); S.trust_env = False
AUTH = os.environ.get("BX_AUTH", "")
URL = "https://ny.solana.dex.blxrbdn.com/api/v2/submit"
MX = "https://margo-swuxg2-fast-mainnet.helius-rpc.com/"
H = "https://mainnet.helius-rpc.com/?api-key=6964ad28-65c3-46f9-9c1e-a713b4ea55ec"
BX_TIP = Pubkey.from_string("HWEoBxYs7ssKuudEjzjmpfJVX7Dvi7wescFsVx2L5yoY")
SYSTEM = Pubkey.from_string("11111111111111111111111111111111")
DEST = Pubkey.from_string("Dh7puYYYfYAMneUwh1jeSgmHNB6XiA1FVk4R9vDpRuiq")

def rpc(url, m, p, timeout=8):
    for _ in range(2):
        try:
            r = S.post(url, json={"jsonrpc":"2.0","id":1,"method":m,"params":p}, timeout=timeout).json()
            if "result" in r:
                return r["result"]
        except Exception:
            pass
    return None

def ts_rfc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

import base58
KP = Keypair.from_bytes(base58.b58decode(os.environ["WALLET_B58"]))
US = KP.pubkey()
print("wallet:", US, flush=True)

# latency probe
t0 = time.time()
try:
    S.get("https://ny.solana.dex.blxrbdn.com/health", timeout=10)
except Exception:
    pass
print(f"connect probe: {int((time.time()-t0)*1000)}ms", flush=True)

N_FIRE = int(os.environ.get("N_FIRE", "1"))
bh = rpc(H, "getLatestBlockhash", [{"commitment":"processed"}])["value"]["blockhash"]

for shot in range(N_FIRE):
    last = None
    while last is None:
        last = rpc(MX, "getMaxShredInsertSlot", [])
        time.sleep(0.03)
    t_b = None; mx_at = None
    while True:
        mx = rpc(MX, "getMaxShredInsertSlot", [])
        if mx is None:
            time.sleep(0.01); continue
        if mx > last:
            t_b = time.time(); mx_at = mx; break
        time.sleep(0.005)
    ixf = Instruction(SYSTEM, (2).to_bytes(4,"little") + (1).to_bytes(8,"little"),
                      [AccountMeta(US, True, True), AccountMeta(DEST, False, True)])
    ixt = Instruction(SYSTEM, (2).to_bytes(4,"little") + (1000000).to_bytes(8,"little"),
                      [AccountMeta(US, True, True), AccountMeta(BX_TIP, False, True)])
    tx = Transaction.new_signed_with_payer([ixf, ixt], US, [KP], Hash.from_string(bh))
    enc = base64.b64encode(bytes(tx)).decode()
    body = {"transaction": {"content": enc}, "skipPreFlight": True,
            "frontRunningProtection": False, "useStakedRPCs": True, "timestamp": ts_rfc()}
    t0 = time.time()
    r = S.post(URL, json=body, headers={"authorization": AUTH, "content-type": "application/json"}, timeout=15)
    send_ms = int((time.time()-t0)*1000)
    delay = int((t0 - t_b)*1000)
    print(f"[{shot}] boundary mx={mx_at} submit +{delay}ms resp {r.status_code} in {send_ms}ms", flush=True)
    if r.status_code == 200:
        sig = r.json()["signature"]
        landed = None
        for _ in range(150):
            time.sleep(0.04)
            st = rpc(H, "getSignatureStatuses", [[sig],{"searchTransactionHistory":False}])
            if st:
                val = (st.get("value") or [None])[0]
                if val and val.get("slot"):
                    landed = val["slot"]; break
        print(f"[{shot}] sig={sig} mx={mx_at} landed={landed} d_mx={(landed-mx_at) if landed else None}", flush=True)
    else:
        print(r.text[:200], flush=True)
    time.sleep(1.5)
