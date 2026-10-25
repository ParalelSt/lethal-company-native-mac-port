#!/usr/bin/env python3
"""Remove Netcode-for-GameObjects IL-post-processor output from decompiled C# so the ILPP can regenerate it.

Removes: __rpc_handler_* , __initializeVariables, __initializeRpcs, __getTypeName methods.
Unwraps [ServerRpc]/[ClientRpc] methods to the statements after `__rpc_exec_stage = __RpcExecStage.Send;`.
Usage: strip_ngo_ilpp.py <dir> [--apply]
"""
import os, re, sys

def skip_literal(s, i):
    """If s[i] starts a string/char/comment, return index just past it; else None."""
    c = s[i]
    if s.startswith("//", i):
        j = s.find("\n", i); return len(s) if j < 0 else j
    if s.startswith("/*", i):
        j = s.find("*/", i + 2); return len(s) if j < 0 else j + 2
    if s.startswith('@"', i) or s.startswith('$@"', i) or s.startswith('@$"', i):
        j = i + (2 if s[i] == '@' else 3)
        while j < len(s):
            if s[j] == '"':
                if j + 1 < len(s) and s[j + 1] == '"': j += 2; continue
                return j + 1
            j += 1
        return len(s)
    if c == '"' or s.startswith('$"', i):
        j = i + (1 if c == '"' else 2)
        while j < len(s):
            if s[j] == '\\': j += 2; continue
            if s[j] == '"': return j + 1
            j += 1
        return len(s)
    if c == "'":
        j = i + 1
        while j < len(s):
            if s[j] == '\\': j += 2; continue
            if s[j] == "'": return j + 1
            j += 1
        return len(s)
    return None

def match_brace(s, open_idx):
    """Return index of the '}' matching the '{' at open_idx."""
    depth = 0; i = open_idx
    while i < len(s):
        j = skip_literal(s, i)
        if j is not None: i = j; continue
        if s[i] == '{': depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0: return i
        i += 1
    raise ValueError("unbalanced braces")

def line_start(s, i):
    return s.rfind("\n", 0, i) + 1

METHOD_REMOVE = re.compile(
    r'^[ \t]*(?:\[[^\]\n]*\][ \t]*\n[ \t]*)*'
    r'(?:private static void __rpc_handler_\d+\s*\([^)]*\)|'
    r'protected override void __initializeVariables\s*\(\)|'
    r'protected override void __initializeRpcs\s*\(\)|'
    r'protected internal override string __getTypeName\s*\(\))'
    r'[ \t]*\n[ \t]*\{', re.M)

RPC_METHOD = re.compile(
    r'^([ \t]*)\[(?:ServerRpc|ClientRpc|Rpc)(?:\([^\n]*\))?\][ \t]*\n'
    r'(?:[ \t]*\[[^\]\n]*\][ \t]*\n)*'
    r'[ \t]*(?:public|private|protected|internal|static|virtual|override|\s)*\s*[\w<>\[\],.]+\s+\w+\s*\((?:[^()]|\([^()]*\))*\)[ \t]*\n[ \t]*\{', re.M)

SEND_MARKER = "__rpc_exec_stage = __RpcExecStage.Send;"

def strip_file(src, log):
    # 1) remove generated methods
    out = []; pos = 0
    for m in METHOD_REMOVE.finditer(src):
        if m.start() < pos: continue
        close = match_brace(src, m.end() - 1)
        start = line_start(src, m.start())
        # eat one preceding blank line
        if start >= 2 and src[start - 2:start] == "\n\n": start -= 1
        out.append(src[pos:start]); pos = close + 1
        if src[pos:pos + 1] == "\n": pos += 1
    out.append(src[pos:]); src = "".join(out)

    # 2) unwrap RPC methods
    out = []; pos = 0; n_ok = n_fail = 0
    for m in RPC_METHOD.finditer(src):
        if m.start() < pos: continue
        body_open = m.end() - 1
        body_close = match_brace(src, body_open)
        body = src[body_open + 1:body_close]
        k = body.find(SEND_MARKER)
        if k < 0:
            if "__rpc_exec_stage" in body:
                n_fail += 1; log.append("NO SEND MARKER: " + src[m.start():m.end()].strip().splitlines()[-2])
            continue  # already clean or not generated
        # innermost enclosing block of the marker: walk back to the '{' whose match encloses k
        # scan from body start, tracking open braces stack
        stack = []; i = 0; enclosing = None
        while i < k:
            j = skip_literal(body, i)
            if j is not None: i = j; continue
            if body[i] == '{': stack.append(i)
            elif body[i] == '}': stack.pop()
            i += 1
        if stack:
            enc_open = stack[-1]; enc_close = match_brace(body, enc_open)
            inner = body[k + len(SEND_MARKER):enc_close]
        else:
            inner = body[k + len(SEND_MARKER):]
        # dedent inner by the depth difference so it sits at method-body level
        indent = m.group(1)
        lines = inner.strip("\n").split("\n")
        # compute minimal leading tabs of non-empty lines
        mins = [len(l) - len(l.lstrip("\t")) for l in lines if l.strip()]
        base = min(mins) if mins else 0
        target = indent + "\t"
        new_lines = [(target + l[base:]) if l.strip() else "" for l in lines]
        new_body = "\n" + "\n".join(new_lines) + "\n" + indent if any(l.strip() for l in lines) else "\n" + indent
        out.append(src[pos:body_open + 1]); out.append(new_body); pos = body_close
        n_ok += 1
    out.append(src[pos:]); src = "".join(out)
    return src, n_ok, n_fail

def run(root, apply=True):
    tot_ok = tot_fail = files = 0; log = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.endswith(".cs"): continue
            p = os.path.join(dp, f)
            s = open(p, encoding="utf-8").read()
            if "__rpc_exec_stage" not in s and "__initializeVariables" not in s and "__getTypeName" not in s:
                continue
            try:
                ns, ok, fail = strip_file(s, log)
            except Exception as e:
                log.append(f"ERROR {p}: {e}"); tot_fail += 1; continue
            leftovers = ns.count("__rpc_exec_stage") + ns.count("__rpc_handler_") + ns.count("__initializeVariables") + ns.count("__getTypeName") + ns.count("__initializeRpcs")
            if leftovers:
                log.append(f"LEFTOVER {leftovers} in {os.path.relpath(p, root)}")
            tot_ok += ok; tot_fail += fail; files += 1
            if apply and ns != s:
                open(p, "w", encoding="utf-8").write(ns)
    gen = os.path.join(root, "__GEN")
    if apply and os.path.isdir(gen):
        import shutil; shutil.rmtree(gen); 
        if os.path.exists(gen + ".meta"): os.remove(gen + ".meta")
    print(f"files: {files}, rpc methods unwrapped: {tot_ok}, failures: {tot_fail}, applied: {apply}")
    for l in log[:40]: print(" ", l)

if __name__ == "__main__":
    run(sys.argv[1], "--apply" in sys.argv)
