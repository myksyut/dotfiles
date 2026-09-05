# CONTEXT.md フォーマット

## 構造

```md
# {コンテキスト名}

{このコンテキストが何であり、なぜ存在するかの1〜2文。}

## Language

**Order（注文）**:
{用語の1〜2文の説明}
_Avoid_: Purchase, transaction

**Invoice（請求書）**:
納品後に顧客へ送る支払い要求。
_Avoid_: Bill, payment request

**Customer（顧客）**:
注文を行う個人または組織。
_Avoid_: Client, buyer, account
```

## ルール

- **意見を持つ。** 同じ概念に複数の言葉があるなら、最良の1つを選び、残りは `_Avoid_` に列挙する
- **定義は締める。** 最大1〜2文。「何であるか」を定義し、「何をするか」は書かない
- **このプロジェクト固有の用語だけ載せる。** 一般的なプログラミング概念（タイムアウト、エラー型、ユーティリティパターン）は、多用していても載せない。追加前に自問する：これはこのコンテキスト固有の概念か、それとも一般概念か？ 前者のみ載せる
- **自然なまとまりが生まれたらサブ見出しでグルーピングする。** 全用語が単一の領域に収まるならフラットなリストでよい

## 単一コンテキスト vs 複数コンテキスト

**単一コンテキスト（大半のリポジトリ）:** リポジトリルートに `CONTEXT.md` を1つ。

**複数コンテキスト:** ルートの `CONTEXT-MAP.md` に、各コンテキストの場所と関係を列挙する：

```md
# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md): 顧客注文の受付と追跡
- [Billing](./src/billing/CONTEXT.md): 請求書の生成と決済処理
- [Fulfillment](./src/fulfillment/CONTEXT.md): 倉庫ピッキングと出荷の管理

## Relationships

- **Ordering → Fulfillment**: Ordering が `OrderPlaced` イベントを発行し、Fulfillment が購読してピッキングを開始
- **Fulfillment → Billing**: Fulfillment が `ShipmentDispatched` イベントを発行し、Billing が購読して請求書を生成
- **Ordering ↔ Billing**: `CustomerId` と `Money` の型を共有
```

構造の推論ルール：

- `CONTEXT-MAP.md` があればそれを読んでコンテキストを特定する
- ルートに `CONTEXT.md` だけあれば単一コンテキスト
- どちらも無ければ、最初の用語が確定したときにルート `CONTEXT.md` を遅延作成する

複数コンテキストの場合、今の話題がどれに属するか推測する。不明なら質問する。
