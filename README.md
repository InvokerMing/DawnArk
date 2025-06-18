# DingTalk Knowledge Auto-Importer

> 自动将文件收录到钉钉 AI 助理知识库的示例项目

## 方案说明

- **核心思路**：
  1. **自定义企业机器人**（推荐）。企业成员只需将文件发送给机器人（或 @机器人 并附带文件），后台即可自动接收 `file` 类型消息。
  2. 服务器通过 **钉钉事件回调** 获取文件 `mediaId` → 下载原文件；
  3. 调用 **钉钉文档/媒体上传 API** 将文件转为可以在线访问的 `docUrl`；
  4. 调用 **AI 助理 LearnKnowledge API** 让助理学习该 `docUrl`；
  5. 给钉钉返回加密后的 `success` 响应，完成一次收录流程。

此方案无需扫描全部群消息，安全性与易用性更佳，也完全符合钉钉开放平台的使用规范。

## 运行步骤

```bash
# 1. 克隆&安装依赖
pip install -r requirements.txt

# 2. 复制 env 模板并填写配置
cp env.example .env
# 编辑 .env 写入 app_key / app_secret / token / aes_key 等信息
# 若需直接在浏览器预览上传文件，请将 PUBLIC_BASE_URL 设置为外网可访问的域名

# 3. 启动服务
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

然后在 **钉钉开放平台 → 应用 → 机器人** 中，将回调地址配置为：

```
https://<你的公网域名>/dingtalk/callback
```

> 需要确保 80/443 端口可达，且 HTTPS 证书有效。

## 目录结构

```
DawnArk/
├── env.example           # 环境变量模板
├── requirements.txt      # Python 依赖
├── README.md
└── src/
    ├── config.py             # 环境变量解析
    ├── dingtalk_client.py    # 钉钉 OpenAPI 调用封装
    ├── dingtalk_crypto.py    # 加解密工具
    ├── knowledge_uploader.py # 知识库写入示例
    └── main.py               # FastAPI 入口
```

## 注意事项

1. **加解密**：示例使用简化版 AES-CBC + PKCS#7，正式环境请对照官方 `DingTalk-Callback-Crypto` 仓库测试。
2. **钉钉文档上传**：若企业已开通正式的文档 API，请替换 `dingtalk_client.upload_doc_and_get_url` 方法。
3. **知识库接口**：API 路径可能更新，请以最新文档为准。
4. **权限**：请在钉钉开放平台为你的应用申请 `Card.Streaming.Write`、`Card.Instance.Write`、`media/upload` 等必要权限。

## License

MIT 