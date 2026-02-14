"""
Phase 1: Root Cause Confirmation — Mandatory Diagnostic Before Fixes.

Sections:
  A) Feature Attribution (permutation importance)
  B) Shortcut Detection (per-group accuracy)
  C) Calibration Curve + Monotonicity (Spearman)
  D) Drift Sensitivity
"""
import sys, os, json, time
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
import torch
import torch.nn as nn
from scipy import stats as scipy_stats


def _build_model(D, device):
    return nn.Sequential(
        nn.Linear(D, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)


def _train(model, features, labels, device, epochs=15):
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    ds = torch.utils.data.TensorDataset(
        torch.tensor(features, dtype=torch.float32),
        torch.tensor(labels, dtype=torch.long),
    )
    loader = torch.utils.data.DataLoader(ds, batch_size=256, shuffle=True)
    model.train()
    for _ in range(epochs):
        for bx, by in loader:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            criterion(model(bx), by).backward()
            optimizer.step()
    return model


def _accuracy(model, features, labels, device):
    model.eval()
    with torch.no_grad():
        x = torch.tensor(features, dtype=torch.float32).to(device)
        preds = model(x).argmax(dim=1).cpu().numpy()
    return float((preds == labels).mean())


def _get_probs(model, features, device):
    model.eval()
    with torch.no_grad():
        x = torch.tensor(features, dtype=torch.float32).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = logits.argmax(dim=1).cpu().numpy()
    return probs, preds


def run_root_cause_analysis(features, labels):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    N, D = features.shape
    np.random.seed(42)
    torch.manual_seed(42)
    
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]
    
    # Train baseline model
    model = _build_model(D, device)
    _train(model, train_f, train_l, device)
    baseline_acc = _accuracy(model, test_f, test_l, device)
    
    lines = [
        "=" * 70,
        "  PHASE 1: ROOT CAUSE CONFIRMATION REPORT",
        "=" * 70,
        f"  Baseline accuracy: {baseline_acc:.4f}",
        f"  Device: {device}",
        "",
    ]
    
    # ===== SECTION A: Feature Attribution (Permutation Importance) =====
    lines += ["-" * 70, "  SECTION A -- Feature Attribution", "-" * 70]
    
    groups = [
        ("signal (0-63)", 0, 64),
        ("response (64-127)", 64, 128),
        ("interaction (128-191)", 128, 192),
        ("noise (192-255)", 192, 256),
    ]
    
    group_importances = {}
    for name, start, end in groups:
        # Shuffle entire group and measure drop
        permuted = test_f.copy()
        for d in range(start, end):
            np.random.shuffle(permuted[:, d])
        perm_acc = _accuracy(model, permuted, test_l, device)
        importance = baseline_acc - perm_acc
        group_importances[name] = importance
        lines.append(f"  {name:<25}: importance={importance:+.4f} (acc={perm_acc:.4f})")
    
    total_imp = sum(abs(v) for v in group_importances.values())
    lines.append("")
    lines.append("  Group Contribution %:")
    for name, imp in group_importances.items():
        pct = abs(imp) / max(total_imp, 1e-10) * 100
        lines.append(f"    {name:<25}: {pct:.1f}%")
    
    interaction_pct = abs(group_importances["interaction (128-191)"]) / max(total_imp, 1e-10) * 100
    lines.append(f"\n  Interaction dominance: {interaction_pct:.1f}% (threshold: <50%)")
    lines.append(f"  SHORTCUT CONFIRMED: {'YES' if interaction_pct > 50 else 'NO'}")
    
    # ===== SECTION B: Shortcut Detection (per-group accuracy) =====
    lines += ["", "-" * 70, "  SECTION B -- Shortcut Detection (Per-Group Accuracy)", "-" * 70]
    
    for name, start, end in groups:
        # Train model using ONLY this group
        group_train = np.zeros_like(train_f)
        group_train[:, start:end] = train_f[:, start:end]
        group_test = np.zeros_like(test_f)
        group_test[:, start:end] = test_f[:, start:end]
        
        group_model = _build_model(D, device)
        _train(group_model, group_train, train_l, device, epochs=10)
        group_acc = _accuracy(group_model, group_test, test_l, device)
        lines.append(f"  {name:<25} only: accuracy={group_acc:.4f}")
    
    # ===== SECTION C: Calibration Curve + Monotonicity =====
    lines += ["", "-" * 70, "  SECTION C -- Calibration Curve + Monotonicity", "-" * 70]
    
    probs, preds = _get_probs(model, test_f, device)
    confidences = probs.max(axis=1)
    n_bins = 10
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    
    bin_confs = []
    bin_accs = []
    lines.append(f"  {'Bin':>12} {'N':>6} {'Conf':>7} {'Acc':>7} {'Gap':>7}")
    
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (confidences >= lo) & (confidences < hi)
        n = int(mask.sum())
        if n > 10:
            conf = float(confidences[mask].mean())
            acc = float((preds[mask] == test_l[mask]).mean())
            gap = conf - acc
            bin_confs.append(conf)
            bin_accs.append(acc)
            lines.append(f"  [{lo:.2f}-{hi:.2f}] {n:6d} {conf:7.4f} {acc:7.4f} {gap:+7.4f}")
    
    # Spearman correlation
    if len(bin_confs) >= 3:
        spearman_r, spearman_p = scipy_stats.spearmanr(bin_confs, bin_accs)
    else:
        spearman_r, spearman_p = 0.0, 1.0
    
    conf_inflation = float(confidences.mean()) - baseline_acc
    is_monotonic = all(bin_accs[i] <= bin_accs[i+1] for i in range(len(bin_accs)-1))
    
    lines += [
        f"",
        f"  Spearman rho:        {spearman_r:.4f} (target >= 0.95)",
        f"  Spearman p-value:    {spearman_p:.6f}",
        f"  Confidence inflation: {conf_inflation:.4f} (target <= 0.03)",
        f"  Monotonic:           {'YES' if is_monotonic else 'NO'}",
    ]
    
    # ===== SECTION D: Drift Sensitivity =====
    lines += ["", "-" * 70, "  SECTION D -- Drift Sensitivity", "-" * 70]
    
    # Novel pattern injection
    novel = test_f.copy()
    n_inject = len(novel) // 5
    novel[:n_inject] = np.random.uniform(0.3, 0.7, (n_inject, D))
    novel_acc = _accuracy(model, novel, test_l, device)
    novel_drop = baseline_acc - novel_acc
    lines.append(f"  Novel patterns (20%): acc={novel_acc:.4f} drop={novel_drop:.4f} (target <0.05)")
    
    # Interaction perturbation
    scrambled = test_f.copy()
    np.random.shuffle(scrambled[:, 128:192])
    scramble_acc = _accuracy(model, scrambled, test_l, device)
    scramble_drop = baseline_acc - scramble_acc
    lines.append(f"  Interaction scramble: acc={scramble_acc:.4f} drop={scramble_drop:.4f} (target <0.05)")
    
    # Scaled features
    scaled = test_f * np.random.uniform(0.85, 1.15, (1, D))
    scaled = np.clip(scaled, 0, 1)
    scaled_acc = _accuracy(model, scaled, test_l, device)
    scaled_drop = baseline_acc - scaled_acc
    lines.append(f"  Feature scaling ±15%: acc={scaled_acc:.4f} drop={scaled_drop:.4f} (target <0.05)")
    
    # ===== SUMMARY =====
    lines += [
        "", "=" * 70,
        "  ROOT CAUSE SUMMARY",
        "=" * 70,
        f"  1. Interaction dominance:    {interaction_pct:.1f}% -- {'FIX REQUIRED' if interaction_pct > 50 else 'OK'}",
        f"  2. Interaction scramble drop: {scramble_drop:.4f} -- {'FIX REQUIRED' if scramble_drop > 0.05 else 'OK'}",
        f"  3. Calibration monotonic:     {'YES' if is_monotonic else 'NO'} (Spearman={spearman_r:.4f}) -- {'FIX REQUIRED' if not is_monotonic or spearman_r < 0.95 else 'OK'}",
        f"  4. Novel pattern drop:        {novel_drop:.4f} -- {'FIX REQUIRED' if novel_drop > 0.05 else 'OK'}",
        "=" * 70,
    ]
    
    report = "\n".join(lines)
    return report, {
        "interaction_dominance_pct": interaction_pct,
        "interaction_scramble_drop": scramble_drop,
        "calibration_spearman": spearman_r,
        "calibration_monotonic": is_monotonic,
        "novel_pattern_drop": novel_drop,
        "confidence_inflation": conf_inflation,
    }


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    
    config = DatasetConfig(total_samples=18000)
    dataset = RealTrainingDataset(config=config)
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()
    
    print(f"Root cause analysis: {len(labels)} samples, {features.shape[1]} dims")
    report, metrics = run_root_cause_analysis(features, labels)
    print(report)
    
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 
                      'reports', 'g38_training', 'root_cause_analysis.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    
    jp = rp.replace('.txt', '.json')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"\nSaved: {rp}")
