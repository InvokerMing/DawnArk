# DingTalk Knowledge Auto-Importer

> 自动将文件收录到钉钉 AI 助理知识库的项目。

## 方案说明

- **核心思路**：
  1. **自定义企业机器人**。企业成员只需将文件发送给机器人，后台即可自动接收 `file` 类型消息。
  2. 服务器通过 **钉钉事件回调（stream模式）** 获取文件消息，自动提取 `senderNick`（发送者姓名）。
  3. 后台自动调用钉钉开放平台接口（目前无法获取userID/unionID）：
      - 先根据 `senderNick` 查询 userID，再查 unionID；
      - 再用 unionID 查询该成员的钉盘个人空间 spaceID；
      - 上传文件到该成员的钉盘空间，获取在线预览 docUrl；
  4. 调用 **AI 助理 LearnKnowledge API** 让助理学习该 `docUrl`；
  5. 给钉钉返回加密后的 `success` 响应，完成一次收录流程。


## 快速开始

### 1. 克隆项目并安装依赖

```bash
git clone https://github.com/InvokerMing/DawnArk
cd DawnArk
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp env.example .env
# 编辑 .env，填写 app_key / app_secret / token / aes_key 等信息
# 若需直接在浏览器预览上传文件，请将 PUBLIC_BASE_URL 设置为外网可访问的域名
```

### 3. 启动服务

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 4. 配置钉钉回调

在机器人应用开发后台，将事件回调与机器人消息推送均配置为stream mode。

## 目录结构

```
DawnArk/
├── env.example           # 环境变量模板
├── requirements.txt      # Python 依赖
├── README.md
└── src/
    ├── config.py             # 环境变量
    ├── dingtalk_client.py    # 钉钉 OpenAPI 调用封装
    ├── stream_listener.py    # stream消息监听器
    ├── knowledge_uploader.py # 知识库写入
    └── main.py               # FastAPI 入口
```

## 注意事项

请在钉钉开放平台为你的应用申请 `Card.Streaming.Write`、`Card.Instance.Write`、`media/upload`、`contact:user:search`、`contact:user:read`、`drive:space:read`、`drive:file:write` 等必要权限。

## 常见问题

- **回调收不到消息？**  
  请检查公网地址、端口、证书、钉钉开放平台配置及服务器日志。
- **文件上传失败？**  
  检查 access_token、权限、API 路径及钉钉开放平台相关配置。

## License

MIT 