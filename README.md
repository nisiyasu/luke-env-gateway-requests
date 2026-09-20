# LUKE QUEST Environment Gateway Request Channel

このrepositoryは、LUKE QUEST Village / Castle / Dungeon のScheduled Agentから
Fenced Mutation Gatewayへ要求を渡すための専用Request Channelです。

## Hard Boundary

- Scheduled Agentはこのrepositoryへrequest draftを追加する。
- Scheduled Agentは `nisiyasu/-luke-quest` へ直接persistent mutationしない。
- Target Repositoryへのdirect writeで403になることはcutover後の正常なCredential Boundary。
- Target Repository側のGatewayだけがLease / Epoch / expected HEAD /
  Evidence Adoption契約を満たしたmutationを適用する。
- 秘密情報、token、credential、Owner個人情報を保存しない。

## Agentが書く場所

AgentはSHA256を自力計算せず、以下へdraftを書く。

`inbox/<lane>/<request_id>.json`

lane:
- `village`
- `castle`
- `dungeon`

Mutation draft schema:

`LUKE_QUEST_ENV_GATEWAY_REQUEST_DRAFT:v1`

Evidence capture draft schema:

`LUKE_QUEST_ENV_EVIDENCE_CAPTURE_REQUEST_DRAFT:v1`

Draftはappend-onlyとして扱い、同じrequest_idの内容を後から書き換えない。

## Draft Finalizer / 下書き確定

`Finalize LUKE QUEST Gateway Drafts`
がdraftを検証し、canonical SHA256を計算して正式requestへ変換する。

Mutation:

`inbox/<lane>/<id>.json`
→ `requests/<lane>/<id>.json`

Evidence Capture:

`inbox/<lane>/<id>.json`
→ `evidence-requests/<lane>/<id>.json`

正式requestが既に存在し内容が異なる場合はappend-only collisionとしてFAILする。

## Mutation Request

Target Repository側Mutation Pollerが

`requests/<lane>/<request_id>.json`

の
`LUKE_QUEST_ENV_GATEWAY_REQUEST:v1`
だけを処理する。

主なoperation:

- `LEASE_ACQUIRE`
- `LEASE_HEARTBEAT`
- `LEASE_RELEASE`
- `IMPLEMENTATION_FILE_UPDATE`
- `ISSUE_COMMENT`
- `ISSUE_CLOSE`
- `PARENT_PROGRESS_UPDATE`
- `EVIDENCE_IDENTIFIERS_RESERVE`
- `DURABLE_EVIDENCE_PUBLISH_FROM_ARTIFACT`
- `EVIDENCE_ADOPT`

画像本体をMutation Requestへbase64で詰めない。

## Evidence Capture Request

`evidence-requests/<lane>/<request_id>.json`

はTarget Repository側のREAD ONLY Evidence Capture Pollerが読む。

Capture前にfresh確認する:

- Lane production enabled
- active Lease
- OWNER_RUN_ID
- Lease Epoch
- unresolved operationなし
- reserved Evidence ID / Adoption ID
- exact implementation HEAD
- fixed Target identity

Artifact名:

`lq-env-evidence-<request_id>`

ArtifactにはTarget / Actual画像、manifest、settings、contract snapshot、runtime auditを含む。

## Visual Audit → Durable Evidence

Scheduled AgentはActions Artifact ZIP本体を取得し、
`target.png` と `actual.png` を実画像として比較する。

PASS時のみ通常Mutation Draftで

`DURABLE_EVIDENCE_PUBLISH_FROM_ARTIFACT`

を送る。

payloadには

- child_issue
- evidence_id
- adoption_id
- expected_evidence_head
- capture_request_id
- artifact_id
- visual_audit
- coordinate_audit

を入れる。

GatewayがTarget Repository ActionsからArtifact本体を直接取得するため、
PNG / ZIPをこのRequest Repositoryへコピーしない。

## Receipt

Target Repository branch:

`gateway/request-receipts`

完了:

`receipts/terminal/<request_id>.json`

再試行待ち:

`receipts/pending/<request_id>.json`

Scheduled Agentはterminal receiptをfresh確認してから次operationへ進む。

## Hard Rules

- request JSONは256 KiB以下
- Target identity / lane / Child Issue / HEAD / Evidence ID / Adoption IDを固定
- 画像本体はRequest Repositoryへ保存しない
- Visual PASSには `visual_comparison_performed=true` が必須
- Durable Evidence保存とfresh read-back完了前にPASS / close / Parent advanceしない
- Target Repositoryへのdirect write権限をScheduled Agentへ戻さない


## Canonical Field / 草原本線の要求経路

草原・王都近郊フィールドのcanonical Build LoopはEnvironment Laneと別の専用経路を使う。

Agentが書く場所:

`field-inbox/<request_id>.json`

Draft schema:

`LUKE_QUEST_CANONICAL_FIELD_GATEWAY_REQUEST_DRAFT:v1`

Request Repository自身の
`Finalize LUKE QUEST Canonical Field Drafts`
が固定Program identityとSHA256を付与して、

`field-requests/<request_id>.json`

へappend-only確定する。

Target Repository側は
`LUKE QUEST Canonical Field Gateway Request Poller`
だけが読む。

安全境界:
- implementation branchは `prototype/modern-3d` 固定
- Parentは #12 固定
- router commentは `5646492352` 固定
- Issue mutationはfresh routerの `CURRENT_PACKET_ISSUE` だけ
- router更新はfresh router body hash一致が必須
- PASS_ADVANCEではCurrent Packetがclosed済みであることをGatewayがfresh確認
- Target RepositoryへのScheduled Agent direct writeは引き続き禁止
- Environment Village / Castle / DungeonのLeaseやrouterへ触れない
