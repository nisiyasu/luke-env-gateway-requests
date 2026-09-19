# LUKE QUEST Environment Gateway Request Channel

このrepositoryは、LUKE QUEST Village / Castle / Dungeon のScheduled Agentから
Fenced Mutation Gatewayへmutation requestを渡すための専用request channelです。

## Hard Boundary

- Agentはこのrepositoryへrequestを追加する。
- Agentは `nisiyasu/-luke-quest` へ直接mutationしない。
- Target Repository側のGatewayだけがrequestを検証し、Lease / Epoch / expected HEAD /
  Evidence Adoption契約を満たしたmutationだけを適用する。
- Target RepositoryのGateway receiptは
  `gateway/request-receipts` branch の `receipts/<request_id>.json` に保存される。

## Request Path

`requests/<lane>/<request_id>.json`

lane:
- `village`
- `castle`
- `dungeon`

Request bodyは `LUKE_QUEST_ENV_GATEWAY_REQUEST:v1` を使用する。

## Important

このrepositoryへ秘密情報、token、credential、Owner個人情報を保存しない。
requestはappend-onlyとして扱い、送信後に同じrequest_idの内容を書き換えない。


## Evidence Request Channel / 証拠要求経路

Mutation requestとは別に、Visual Evidenceは次の2段階で扱う。

1. `evidence-requests/<lane>/<request_id>.json`
   - exact implementation HEAD / child Issue / EVIDENCE_ID / ADOPTION_ID を指定
   - Target Repository側のREAD ONLY Evidence Workflowを起動するための要求
   - 画像本体はこのrepositoryへ保存しない

2. `evidence-publish/<lane>/<request_id>.json`
   - Scheduled AgentがActions ArtifactのTarget/Actualを実画像で監査した後、
     PASSした `visual_audit` / `coordinate_audit` と採用対象identityだけを送る
   - Target Repository側GatewayがActions Artifact本体を取得し、
     Durable Evidenceへappend-only保存してからEvidence Adoptionへ進む

### Hard Rules

- PNG / ZIP / base64画像本体をRequest Repositoryへ持ち込まない
- request JSONは256 KiB以下
- Target identity / lane / child Issue / HEAD / Evidence ID / Adoption IDを固定する
- Visual PASSには `visual_comparison_performed=true` が必須
- Durable Evidence保存とfresh read-back完了前にChild PASS / close / Parent advanceを行わない
