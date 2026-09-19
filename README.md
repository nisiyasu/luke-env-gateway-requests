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
