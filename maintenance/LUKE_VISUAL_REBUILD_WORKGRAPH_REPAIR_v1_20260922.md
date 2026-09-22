# LUKE 視覚再構築 Work Graph 修復パケット v1

STATUS: REQUIRED_REPAIR
TARGET_REPOSITORY: nisiyasu/-luke-quest
PARENT: #101
SPEC_BRANCH: spec/target-image-to-threejs-20260921
CREATED_AT: 2026-09-22

## 1. Freshで確認した不具合

### A. Native Dependenciesの順序逆転
現行:
- #103 blocked_by #102
- #104 blocked_by #103
- #105 blocked_by #103
- #113 blocked_by #104
- #114 blocked_by #113
- #115 blocked_by #114
- #116 blocked_by #112, #115

この形ではWork Graph/ExtensionがG0後になり、DEVELOPMENT_PIPELINE_v1の
Task→GitHub Work Graph → Extension → Agent implementation
という工程順と矛盾する。

### B. 修復後のNative Dependencies
- #113 blocked_by #102
- #114 blocked_by #113
- #103 blocked_by #114
- #104 blocked_by #103
- #105 blocked_by #103
- #106 blocked_by #104, #105
- 以後のG1〜G7は既存の視覚Gate順を維持
- #115 blocked_by #112
- #116 blocked_by #112, #115

#115はT105-T108のAgent実行プロセス最終監査として扱い、通常のleaf implementation Issueとして早期claimしない。

## 2. Spec Kit Extension不具合
specs/001-target-image-threejs/extensions/project_work_graph.py はmanaged dependencyを追加するだけで、
desired graphから消えたobsolete managed dependencyをremoveしない。

必要修正:
- managed issue set = #102〜#116 の範囲を明示
- desired dependency setをissue-graph.jsonから生成
- current managed dependency setとの差分を計算
- obsolete edgeはdry-runで dependency_remove として表示
- --apply時だけGitHub REST DELETE
  /repos/{owner}/{repo}/issues/{blocked}/dependencies/blocked_by/{blocking_issue_id}
  を実行
- external/unmanaged dependencyは削除しない
- apply後再dry-run planned_count=0 を要求

## 3. stale execution boundary
以下の文書に旧停止点が残る:
- DEVELOPMENT_PIPELINE_v1.md
- issue-map.md

旧記述:
- Step 22で停止
- T105以降のAgent実装を開始しない

Ownerはその後Agent実装・READY Pull運用への昇格を明示承認済み。
正本更新が必要。

## 4. Worker claim継続不具合
Worker Aは#102 claim terminal receipt成功後、そのrunで実作業へ進まず終了した。
claim成功をrun終了条件にしない。

Schedule Promptへ反映済み:
- claim成功 = 作業開始条件
- 同runでCURRENT_WORKへ続行
- repair gate未解消時はclose/advance禁止

## 5. T106 branch/worktree separation未達
Fresh確認:
- Worker A専用branch: なし
- Worker B専用branch: なし
- Worker C専用branch: なし
- Issue別work branch: なし
- 3Workerとも experiment/target-image-threejs-v1 を共有

Shared Leaseは衝突防止にはなるが、3Workerの並列実装にはならない。

必要:
- #103 Safe Resetまでは単一Writer可
- #104/#105の並列READY前に独立work branchを確立
- local実行時は独立worktree
- safe integration/PR/merge経路を検証
- 分離未成立中は複数Workerの同時code mutation禁止

## 6. #103 Fresh Reality
- archive/pre-target-image-rebuild-20260921 は prototype/modern-3d とidentical
- experiment/target-image-threejs-v1 はarchiveより1 commit ahead
- 差分は docs/autonomy/evidence/VISUAL_REBUILD_GATEWAY_CANARY_v1.txt のみ
- ReuseInventory / old scene cutover / rollback evidenceは未確認

## 7. Gateway/Receipt Fresh Reality
visual-rebuild lane:
- implementation branch: experiment/target-image-threejs-v1
- control branch: control/lease-visual-rebuild
- production enabled: true
- Receipt branch: gateway/request-receipts
- Worker C run18 LEASE_ACQUIRE: ok=true, epoch=17
- Worker A run13 LEASE_ACQUIRE: ok=true, epoch=18
- Worker A run13 #102 claim: CONFIRMED_APPLIED
- #102 current claim owner: Worker A

B/CはAの有効claim後、新規Lease要求を出しておらず重複claim防止は動作。

## 8. Optional efficiency cleanup
Finalize LUKE QUEST Gateway Drafts成功時に
environment-visual-evidence-production.ymlまで毎回dispatchしている。
Lease/Issue commentだけでもEvidence workflowが起動しActions noiseが増える。
正しさのP0ではないため、P0修復後に軽量化する。

## 9. 修復順
1. Native dependency修復
2. issue-graph.json / issue-map.md / Issue trace fields同期
3. Extensionにmanaged obsolete dependency removal追加
4. Extension dry-run
5. Extension apply
6. post dry-run planned_count=0
7. DEVELOPMENT_PIPELINE_v1.mdのexecution boundary更新
8. #102 fresh acceptance監査・evidence・close
9. #113/#114 fresh evidenceでclose
10. #103を単一Writerで実行
11. #104/#105並列前にbranch/worktree separationを完成
12. 3Worker READY Pullを本運用

## 10. Safety
- Target direct write credential boundaryは維持
- DCR offline中に裏口を作らない
- 旧#12/#51/#52/#53へ戻らない
- Ownerを通常defect detectorとして使わない
