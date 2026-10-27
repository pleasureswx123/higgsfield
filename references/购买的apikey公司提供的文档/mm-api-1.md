# MM 模型接口文档

本网关通过 OpenAI 兼容接口统一对接 MM 的多种模型能力。

---

## 公共说明

### 基础地址

```
http://llm-gw.videoplus.cc
```

### 公共请求头

所有接口均需携带以下 Header：

| Header | 必填 | 说明 |
|--------|:----:|------|
| `Authorization` | 是 | `Bearer <your-key>`，由管理员分发的 API Key |
| `Content-Type` | 是 | `application/json` |
| `X-Biz-Id` | 是 | 业务标识，用于区分不同业务线的调用，值为 `op` |

### 公共请求格式

所有生成类接口统一使用 `POST /v1/chat/completions`，请求体结构：

```json
{
  "model": "<模型名>",
  "messages": [
    { "role": "user", "content": "<内容>" }
  ],
  "<可选参数1>": "<值>",
  "<可选参数2>": "<值>"
}
```

> 可选参数与 `model`、`messages` 同级，放在请求体顶层。

---

## 一、多模态对话（Gemini 系列）

支持文本对话 + 图文理解，兼容 OpenAI 多模态消息格式。

### 接口信息

| 项目 | 值 |
|------|-----|
| URL | `POST /v1/chat/completions` |
| 鉴权 | `Authorization: Bearer <your-key>` |
| Content-Type | `application/json` |

### 可用模型

| 模型名 | 说明 |
|--------|------|
| `mm-gemini-2.5-f` | 多模态对话（Flash） |
| `mm-gemini-3.0-p` | 多模态对话（Pro） |
| `mm-gemini-3.1-f` | 多模态对话（Flash） |

### 请求参数

#### 必填参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型名，如 `"mm-gemini-3.0-p"` |
| `messages` | array | 消息列表，格式见下方 |

#### messages 格式

**纯文本**：

```json
{
  "model": "mm-gemini-3.0-p",
  "messages": [
    { "role": "user", "content": "你好" }
  ]
}
```

**图文多模态**：

```json
{
  "model": "mm-gemini-3.0-p",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "请描述这张图片" },
        { "type": "image_url", "image_url": { "url": "https://s.alicdn.com/@sc04/kf/H465d4cbb58b647fc9cb0858ab2b3136eS.jpg_350x350.jpg" } }
      ]
    }
  ]
}
```

图片支持 URL 和 base64 两种方式：
- URL：`"url": "https://example.com/img.jpg"`
- Base64：`"url": "data:image/jpeg;base64,/9j/4AAQ..."`

支持的文件类型：
- 图片：`image/png`、`image/jpeg`、`image/webp`
- 视频：`video/mp4`、`video/mov`、`video/mpeg`、`video/avi`
- 音频：`audio/mp3`、`audio/mpeg`、`audio/wav`
- 文档：`application/pdf`、`text/plain`

输入限制：
- 内联图片（base64）：单张 ≤ 7MB
- URL 文件（音视频/文档）：≤ 15MB
- 参考图片数量：canvas-25-f 最多 3 张，canvas-30-p 最多 14 张

#### 可选参数

##### 生成配置（generationConfig）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `temperature` | float | 1.0 | 采样温度，范围 0~2，越低越确定 |
| `topP` | float | 0.95 | 核采样概率（0~1） |
| `topK` | int | — | Top-K 采样候选数 |
| `maxOutputTokens` | int | — | 最大输出 token 数 |
| `candidateCount` | int | 1 | 候选回复数量（最多 8） |
| `stopSequences` | array | — | 停止序列列表（最多 5 个），如 `["\n"]` |
| `presencePenalty` | float | 0 | 存在惩罚（-2.0~2.0） |
| `frequencyPenalty` | float | 0 | 频率惩罚（-2.0~2.0） |
| `responseMimeType` | string | `"text/plain"` | 响应格式：`"text/plain"` / `"application/json"` / `"text/x.enum"` |
| `responseSchema` | object | — | 响应 JSON Schema（需配合 `responseMimeType: "application/json"` 使用） |
| `imageConfig` | object | — | 图片生成配置，含 `AspectRatio`（`"1:1"`/`"16:9"` 等）和 `ImageSize`（`"1K"`/`"2K"`/`"4K"`） |

##### 高级参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `systemInstruction` | object | 系统指令，格式 `{"parts": [{"text": "你是..."}]}` |
| `tools` | array | 工具列表（Function Calling） |
| `safetySettings` | array | 安全设置，如 `[{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}]` |
| `cachedContent` | string | 缓存内容标识 |

### 完整请求示例

```
POST http://llm-gw.videoplus.cc/v1/chat/completions
Headers:
  Authorization: Bearer <your-key>
  Content-Type: application/json
  X-Biz-Id: op
```

```json
{
  "model": "mm-gemini-3.0-p",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "请描述这张图片的内容" },
        { "type": "image_url", "image_url": { "url": "https://s.alicdn.com/@sc04/kf/H465d4cbb58b647fc9cb0858ab2b3136eS.jpg_350x350.jpg" } }
      ]
    }
  ],
  "temperature": 0.7,
  "topP": 0.9,
  "maxOutputTokens": 1024
}
```

### 响应格式

标准 OpenAI chat completion 格式：

```json
{
  "id": "chatcmpl-xxxxxxxx",
  "model": "mm-gemini-3.0-p",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "这张图片展示了..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 258,
    "completion_tokens": 150,
    "total_tokens": 408
  }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 请求唯一标识 |
| `model` | string | 使用的模型名 |
| `choices[].message.content` | string | 模型生成的文本回复 |
| `choices[].finish_reason` | string | 结束原因：`"stop"` 正常结束 |
| `usage.prompt_tokens` | int | 输入消耗的 token 数 |
| `usage.completion_tokens` | int | 输出消耗的 token 数 |
| `usage.total_tokens` | int | 总 token 数 |

---

## 二、图片生成

通过文本描述生成图片，也支持参考图片进行风格转换。

### 接口信息

| 项目 | 值 |
|------|-----|
| URL | `POST /v1/chat/completions` |
| 鉴权 | `Authorization: Bearer <your-key>` |
| Content-Type | `application/json` |

### 可用模型

| 模型名 | 说明 |
|--------|------|
| `mm-imagen2` | 文生图 / 图生图 |

### 请求参数

#### 必填参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 固定为 `"mm-imagen2"` |
| `messages` | array | 消息列表，格式见下方 |

#### messages 格式

**文生图**（纯文本提示词，最长 32,000 字符）：

```json
{
  "model": "mm-imagen2",
  "messages": [
    { "role": "user", "content": "一只橘猫趴在窗台上晒太阳，水彩风格" }
  ]
}
```

**图生图 / 图片编辑**（参考图 + 文本描述，支持最多 16 张输入图片）：

```json
{
  "model": "mm-imagen2",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "将这张照片加一只小狗" },
        { "type": "image_url", "image_url": { "url": "https://s.alicdn.com/@sc04/kf/H25c22c8700e640ec948f812591164b3fE.jpg_350x350.jpg" } }
      ]
    }
  ]
}
```

> 当 messages 中包含 `image_url` 时，自动切换到图片编辑端点（canvas-20 edits API）。网关会自动下载图片并以 multipart/form-data 格式上传。

图片支持 URL 和 base64：
- URL：`"url": "https://example.com/img.jpg"`
- Base64：`"url": "data:image/jpeg;base64,/9j/4AAQ..."`

#### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `n` | int | 1 | 生成图片数量，范围 1~10，每张单独计费 |
| `size` | string | `"auto"` | 图片尺寸：`"auto"` / `"1024x1024"` / `"1536x1024"` / `"1024x1536"` / `"2048x2048"` / `"2048x1152"` / `"3840x2160"` 或自定义（最大边≤3840，双边为16的倍数，宽高比≤3:1） |
| `quality` | string | `"auto"` | 画质：`"low"` / `"medium"` / `"high"` / `"auto"` |
| `output_format` | string | `"png"` | 输出格式：`"png"` / `"jpeg"` / `"webp"` |
| `output_compression` | int | — | 压缩比（0~100，仅 jpeg/webp 有效） |
| `moderation` | string | `"auto"` | 内容审核级别：`"auto"` 标准过滤 / `"low"` 放宽过滤 |

### 完整请求示例

**文生图：**

```
POST http://llm-gw.videoplus.cc/v1/chat/completions
Headers:
  Authorization: Bearer <your-key>
  Content-Type: application/json
  X-Biz-Id: op
```

```json
{
  "model": "mm-imagen2",
  "messages": [
    {
      "role": "user",
      "content": "一只橘猫趴在窗台上晒太阳，水彩风格"
    }
  ],
  "n": 2,
  "size": "1024x1024",
  "quality": "high",
  "output_format": "png"
}
```

**图生图（带可选参数）：**

```json
{
  "model": "mm-imagen2",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "将这张照片转换为赛博朋克风格" },
        { "type": "image_url", "image_url": { "url": "https://s.alicdn.com/@sc04/kf/H25c22c8700e640ec948f812591164b3fE.jpg_350x350.jpg" } }
      ]
    }
  ],
  "n": 1,
  "size": "1024x1024",
  "quality": "high",
  "output_format": "jpeg",
  "output_compression": 90
}
```

### 响应格式

标准 chat completion 格式，`choices[0].message.content` 为 JSON 字符串：

```json
{
  "id": "chatcmpl-xxxxxxxx",
  "model": "mm-imagen2",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"images\": [...], \"output_format\": \"png\", \"size\": \"1024x1024\", \"usage\": {...}}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

#### content 解析后的结构

```json
{
  "images": [
    {
      "b64_json": "<base64 编码的图片数据>",
      "revised_prompt": "优化后的提示词"
    },
    {
      "b64_json": "<base64 编码的图片数据>",
      "revised_prompt": "优化后的提示词"
    }
  ],
  "output_format": "png",
  "size": "1024x1024",
  "usage": {
    "input_tokens": 120,
    "output_tokens": 4096,
    "total_tokens": 4216,
    "input_tokens_details": { "text_tokens": 120, "image_tokens": 0 }
  }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `images[].b64_json` | string | Base64 编码的图片数据，前端可直接用 `data:image/png;base64,` 前缀渲染 |
| `images[].revised_prompt` | string | 模型优化后的提示词 |
| `output_format` | string | 图片格式 |
| `size` | string | 图片尺寸 |
| `usage.input_tokens` | int | 输入 token |
| `usage.output_tokens` | int | 输出 token |
| `usage.total_tokens` | int | 总 token |

> ⚠️ **注意**：canvas-20 仅返回 `b64_json`，不支持返回 URL。当 `n>1` 时响应体较大（每张 1024x1024 PNG 约 1~3MB base64），建议使用 `output_format: "jpeg"` 配合 `output_compression` 减小体积。

---

## 三、视频生成

异步任务模式：先创建任务获取 ID，再轮询任务状态获取结果。

### 可用模型

| 模型名 | 说明 | 区域 | 支持分辨率 |
|--------|------|------|-----------|
| `mm-h3` | H3 多模态视频生成 V2 | 国际站 | 2K |
| `mm-eva-sd-2.0` | 标准版，全能力高质量输出 | 国际站 | 480p / 720p / 1080p |
| `mm-eva-sd-2.0-fast` | 快速版，低延迟 | 国际站 | 480p / 720p（**不支持 1080p**） |
| `mm-eva-sd-2.5` | 2.5 标准版，全能力高质量输出 | 国际站 | 480p / 720p / 1080p |
| `mm-eva-sd-2.5-fast` | 2.5 快速版，低延迟 | 国际站 | 480p / 720p（**不支持 1080p**） |
| `mm-nova-sd-2.0` | 标准版，全能力高质量输出 | 国内站 | 480p / 720p / 1080p |
| `mm-nova-sd-2.0-fast` | 快速版，低延迟 | 国内站 | 480p / 720p（**不支持 1080p**） |
| `mm-nova-sd-2.5` | 2.5 标准版，全能力高质量输出 | 国内站 | 480p / 720p / 1080p |
| `mm-nova-sd-2.5-fast` | 2.5 快速版，低延迟 | 国内站 | 480p / 720p（**不支持 1080p**） |

> 2.5 系列的接口参数与对应 2.0 版本一致，收费标准也与对应 2.0 版本相同：标准版按 `$7 / 1M output tokens` 计费，Fast 版按 `$5.6 / 1M output tokens` 计费。

> `mm-h3` 使用国际站 Video Generation V2 接口；`mm-eva-sd-*` 走国际站旧版接口，`mm-nova-sd-*` 走国内站旧版接口。两站 Key 不互通。

#### H3（Video Generation V2）说明

`mm-h3` 提交到 mm `/v2/video_generation`，查询使用 `/v2/query/video_generation/{task_id}`。网关仍统一暴露：

- 创建：`POST /v1/chat/completions`
- 查询：`GET /v1/video/tasks/{task_id}`

H3 约束：

- 每次请求必须包含非空文本提示词。
- `resolution` 固定为 `"2K"`，`duration` 必填且为 4~15 秒整数。
- 纯文生视频必须传具体 `ratio`，不能使用 `adaptive`。
- 首尾帧模式与参考素材模式不能混用；可单独提供首帧、尾帧，或同时提供首尾帧。
- 最多 9 张参考图、3 个参考视频、3 段参考音频；参考音频不能单独使用。
- 不支持 `callback_url`；网关不会向 H3 下游转发该字段。
- H3 不接收旧版 SD2 的 `bitrate_mode`、`generate_audio` 等参数，网关不会向 H3 下游转发。

H3 文生视频示例：

```json
{
  "model": "mm-h3",
  "messages": [
    { "role": "user", "content": "电影感太空歌剧预告片，舰队跃迁离开" }
  ],
  "resolution": "2K",
  "duration": 5,
  "ratio": "16:9"
}
```

H3 首尾帧示例：

```json
{
  "model": "mm-h3",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "镜头平滑推进，人物转身看向镜头" },
        { "type": "image_url", "image_url": { "url": "https://example.com/first.png" }, "role": "first_frame" },
        { "type": "image_url", "image_url": { "url": "https://example.com/last.png" }, "role": "last_frame" }
      ]
    }
  ],
  "resolution": "2K",
  "duration": 5,
  "ratio": "adaptive"
}
```

H3 查询成功时，结果位于 `task` 对象，视频下载地址为 `task.content.url`，计费信息为 `task.usage`。下载 URL 有时效，建议及时转存。任务仅可查询最近 7 天。

H3 2K 按秒计费：输出及参考视频均为 `$0.13/秒`；输入图片前 5 张免费，超出部分 `$0.04/张`；音频免费。网关在任务首次查询成功时记录费用。

---

### 第一步：创建视频任务

#### 接口信息

| 项目 | 值 |
|------|-----|
| URL | `POST /v1/chat/completions` |
| 鉴权 | `Authorization: Bearer <your-key>` |
| Content-Type | `application/json` |

#### 请求参数

##### 必填参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型名，如 `"mm-nova-sd-2.0"` |
| `messages` | array | 消息列表，格式见下方 |

##### messages 格式

支持的多模态组合：
- 纯文本
- 文本（可选）+ 图片
- 文本（可选）+ 视频
- 文本（可选）+ 图片 + 音频
- 文本（可选）+ 图片 + 视频
- 文本（可选）+ 视频 + 音频
- 文本（可选）+ 图片 + 视频 + 音频

> ⚠️ 音频不能单独存在，必须搭配文本/图片/视频。

**文生视频**（纯文本提示词）：

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    { "role": "user", "content": "一只金毛犬在海边奔跑，夕阳西下" }
  ]
}
```

**图生视频 - 首帧驱动**：

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "让画面中的人物跳舞" },
        { "type": "image_url", "image_url": { "url": "https://s.alicdn.com/@sc04/kf/H465d4cbb58b647fc9cb0858ab2b3136eS.jpg_350x350.jpg" }, "role": "first_frame" }
      ]
    }
  ]
}
```

**图生视频 - 参考图风格**：

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "根据参考图生成一段奶茶广告" },
        { "type": "image_url", "image_url": { "url": "https://s.alicdn.com/@sc04/kf/S7b733abe49c44b489d5aae6d694af7cb0.jpg_300x300.jpg" }, "role": "reference_image" }
      ]
    }
  ]
}
```

**视频参考**：

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "参考这个视频风格，生成奶茶特写镜头" },
        { "type": "video_url", "video_url": { "url": "https://videos.pexels.com/video-files/8004729/8004729-hd_1080_1920_25fps.mp4" }, "role": "reference_video" }
      ]
    }
  ]
}
```

**音频参考**（必须搭配图片/视频/文本）：

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "第一人称奶茶广告" },
        { "type": "image_url", "image_url": { "url": "https://vcg00.cfp.cn/creative/vcg/800/new/VCG211455423333.jpg" }, "role": "reference_image" },
        { "type": "audio_url", "audio_url": { "url": "https://assets.699pic.com/public/img95/music_sound_effect/056/561/5d677251488f6.mp3" }, "role": "reference_audio" }
      ]
    }
  ]
}
```

##### content 项 role 值说明

| type | role 值 | 说明 |
|------|---------|------|
| `image_url` | `first_frame` | 用作视频首帧（默认） |
| `image_url` | `reference_image` | 用作风格/内容参考 |
| `video_url` | `reference_video` | 视频参考（激活 V2V 模式） |
| `audio_url` | `reference_audio` | 音频参考 |

> 如果不指定 `role`，`image_url` 默认为 `first_frame`，`video_url` 默认为 `reference_video`，`audio_url` 默认为 `reference_audio`。

图片/视频/音频支持 URL 和 base64：
- URL：`"url": "https://example.com/img.jpg"`
- Base64：`"url": "data:image/jpeg;base64,/9j/4AAQ..."`

##### 可选参数（输出控制）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `resolution` | string | `"720p"` | 分辨率：`"480p"` / `"720p"` / `"1080p"`（fast 版不支持 1080p） |
| `duration` | int | 5 | 视频时长（秒），范围 4~15，`-1` 表示由模型自动决定 |
| `ratio` | string | `"adaptive"` | 画面比例：`"16:9"` / `"9:16"` / `"4:3"` / `"3:4"` / `"1:1"` / `"21:9"` / `"adaptive"` |
| `generate_audio` | bool | true | 是否生成同步音频（语音/音效/BGM） |
| `bitrate_mode` | string | `"standard"` | 视频画质档位：`"standard"` 为标准画质，平衡画质与体积；`"high"` 为高清画质，保留更多细节、减少压缩伪影，输出体积约增加 3~5 倍。仅 SD2 模型支持，网关不校验并原样透传给 |
| `seed` | int | -1 | 随机种子（-1 为随机，相同种子+相同参数可接近复现） |
| `watermark` | bool | false | 是否加 AI 生成水印 |

##### 可选参数（任务控制）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
> 不支持 `callback_url`；网关会忽略该字段，请通过任务查询接口轮询状态。

| `return_last_frame` | bool | false | 是否返回视频最后一帧（可用作下一段视频的首帧，实现连续视频） |
| `service_tier` | string | `"default"` | 服务等级 |
| `execution_expires_after` | int | 172800 | 任务超时时间（秒），范围 3600~259200 |
| `safety_identifier` | string | — | 终端用户唯一标识（≤64字符），建议传哈希后的用户ID |
| `tools` | array | — | 工具列表，如 `[{"type": "web_search"}]`（仅 nova 系列支持） |

#### 完整请求示例

```
POST http://llm-gw.videoplus.cc/v1/chat/completions
Headers:
  Authorization: Bearer <your-key>
  Content-Type: application/json
  X-Biz-Id: op
```

**文生视频：**

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    {
      "role": "user",
      "content": "一只金毛犬在海边奔跑，夕阳西下"
    }
  ],
  "resolution": "720p",
  "duration": 6,
  "ratio": "16:9",
  "generate_audio": true,
  "bitrate_mode": "high"
}
```

**多模态（文本 + 图片 + 音频）：**

```json
{
  "model": "mm-nova-sd-2.0",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "第一人称奶茶广告，镜头推近看到奶盖和茶的分层" },
        { "type": "image_url", "image_url": { "url": "https://vcg00.cfp.cn/creative/vcg/800/new/VCG211455423333.jpg" }, "role": "reference_image" },
        { "type": "audio_url", "audio_url": { "url": "https://assets.699pic.com/public/img95/music_sound_effect/056/561/5d677251488f6.mp3" }, "role": "reference_audio" }
      ]
    }
  ],
  "resolution": "1080p",
  "duration": 11,
  "ratio": "16:9",
  "generate_audio": true
}
```

#### 成功响应

```json
{
  "id": "chatcmpl-d9722f49-480d-4aec-b251-14af9b4afa64-1780390812000",
  "model": "mm-nova-sd-2.0",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"id\": \"chatcmpl-d9722f49-...-1780390812000\", \"model\": \"nova-video-2.0\", \"status\": \"queued\", \"created_at\": 1780390812}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

**关键**：从 `choices[0].message.content` 解析 JSON，获取 `id` 字段即为 **任务 ID**，用于下一步轮询。

#### 失败响应

创建失败时接口直接返回 HTTP 400/500 错误：

```json
{
  "error": {
    "message": "invalid params, invalid resolution=768P, allowed: 480p / 720p / 1080p",
    "type": null,
    "code": "500"
  }
}
```

---

### 第二步：轮询任务结果

#### 接口信息

| 项目 | 值 |
|------|-----|
| URL | `GET /v1/video/tasks/{task_id}` |
| 鉴权 | `Authorization: Bearer <your-key>` |

#### 请求参数

| 参数 | 位置 | 必填 | 说明 |
|------|------|:----:|------|
| `task_id` | URL 路径 | 是 | 第一步返回的任务 ID |

> 无需传 `model` 参数，系统会自动从数据库中查找对应模型。

#### 完整请求示例

```
GET http://llm-gw.videoplus.cc/v1/video/tasks/chatcmpl-d9722f49-480d-4aec-b251-14af9b4afa64-1780390812000
Headers:
  Authorization: Bearer <your-key>
```

#### 建议轮询策略

- 轮询间隔：30~60 秒（过于频繁会消耗 RPM 配额）
- 超时时间：视频生成通常 5~20 分钟

#### 响应示例（生成中）

```json
{
  "id": "chatcmpl-d9722f49-...",
  "model": "nova-video-2.0",
  "status": "in_progress",
  "created_at": 1780383044,
  "updated_at": 1780383060
}
```

#### 响应示例（生成成功）

```json
{
  "id": "chatcmpl-d9722f49-...",
  "model": "nova-video-2.0",
  "status": "succeeded",
  "content": {
    "video_url": "https://xxx.com/video.mp4?signed..."
  },
  "usage": {
    "completion_tokens": 108900,
    "total_tokens": 108900
  },
  "created_at": 1780383044,
  "updated_at": 1780383159,
  "seed": "40413",
  "ratio": "16:9",
  "resolution": "720p",
  "duration": 5,
  "generate_audio": true
}
```

#### 响应示例（生成失败）

```json
{
  "id": "chatcmpl-d9722f49-...",
  "model": "nova-video-2.0",
  "status": "failed",
  "error": {
    "code": "INVALID_PROMPT",
    "message": "Prompt contains restricted content"
  },
  "created_at": 1780383044,
  "updated_at": 1780383060
}
```

#### 状态值说明

| status | 含义 | 处理方式 |
|--------|------|---------|
| `queued` | 排队中 | 继续轮询 |
| `running` / `in_progress` | 生成中 | 继续轮询 |
| `succeeded` / `completed` | 生成成功 | 从 `content.video_url` 获取视频 |
| `failed` | 生成失败 | 检查 `error.message` 了解原因，修改提示词后重试 |
| `expired` | 任务超时 | 重新提交 |

#### 成功响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 任务 ID |
| `model` | string | 模型名 |
| `status` | string | 任务状态 |
| `content.video_url` | string | 视频下载链接（带签名，**有效期约 24 小时**） |
| `usage.completion_tokens` | int | 实际计费 token 数 |
| `usage.total_tokens` | int | 总 token 数 |
| `resolution` | string | 实际生成的分辨率 |
| `duration` | int | 实际视频时长（秒） |
| `ratio` | string | 画面比例 |
| `seed` | string | 随机种子（可用于复现） |
| `generate_audio` | bool | 是否生成了音频 |
| `created_at` | int | 任务创建时间（Unix 时间戳） |
| `updated_at` | int | 任务更新时间（Unix 时间戳） |

#### 注意事项

- `video_url` 为带签名的临时链接，**有效期约 24 小时**，请及时下载保存
- 内容审核失败（`INVALID_PROMPT` / `BLOCKED_BY_MODERATION`）不要盲目重试，需修改提示词
- 轮询接口有鉴权校验，必须使用创建任务时的同一个 Key
- `ratio: "adaptive"` 时实际比例由模型自动选择，会在响应中回填

---

### 分辨率与像素对照表

| 分辨率 | 16:9 | 9:16 | 4:3 | 3:4 | 1:1 | 21:9 |
|--------|------|------|-----|-----|-----|------|
| 480p | 864×496 | 496×864 | 752×560 | 560×752 | 640×640 | 992×432 |
| 720p | 1280×720 | 720×1280 | 1112×834 | 834×1112 | 960×960 | 1470×630 |
| 1080p | 1920×1080 | 1080×1920 | 1664×1248 | 1248×1664 | 1440×1440 | 2206×946 |

---

## 四、同步语音合成

推荐接口：`POST /v1/speech/t2a`。模型已注册到 LiteLLM，控制台和虚拟卡白名单可见。

### 接口信息

| 项目 | 值 |
|------|-----|
| URL | `POST /v1/speech/t2a` |
| 鉴权 | `Authorization: Bearer <your-key>` |
| Content-Type | `application/json` |

### 可用模型

| 模型名 | 说明 | 单价 |
|--------|------|------|
| `mm-2.8-hd` | 高质量 | `$100 / 1M` 计费字符 |
| `mm-2.8-turbo` | 低延迟 | `$60 / 1M` 计费字符 |
| `mm-2.6-hd` | 高质量 | `$100 / 1M` 计费字符 |
| `mm-2.6-turbo` | 低延迟 | `$60 / 1M` 计费字符 |
| `mm-02-hd` | 高质量 | `$100 / 1M` 计费字符 |
| `mm-02-turbo` | 低延迟 | `$60 / 1M` 计费字符 |

费用取响应 `extra_info.usage_characters`，不是 `word_count`。

### 请求示例

```
POST http://llm-gw.videoplus.cc/v1/speech/t2a
Headers:
  Authorization: Bearer <your-key>
  Content-Type: application/json
```

```json
{
  "model": "mm-2.8-turbo",
  "text": "你好，这是一段语音合成测试。",
  "stream": false,
  "language_boost": "auto",
  "output_format": "hex",
  "voice_setting": {
    "voice_id": "English_expressive_narrator",
    "speed": 1,
    "vol": 1,
    "pitch": 0
  },
  "audio_setting": {
    "sample_rate": 32000,
    "bitrate": 128000,
    "format": "mp3",
    "channel": 1
  }
}
```

`text` 最长 10000 字符。`voice_setting.voice_id` 必填。非流式可将 `output_format` 设为 `url`，下载地址约 24 小时有效。

### 响应要点

- `data.audio`：十六进制音频，或 `output_format=url` 时为下载地址
- `extra_info.usage_characters`：计费字符数
- `trace_id`：排查用

---

## 五、错误码

| status_code | 含义 | 处理方式 |
|:-----------:|------|---------|
| 0 | 成功 | - |
| 1002 | 触发限流 | 稍后重试 |
| 1004 | 鉴权失败 | 检查 API Key 是否正确 |
| 1026 | 输入含敏感内容 | 修改输入内容 |
| 1027 | 生成结果含敏感内容 | 更换提示词重试 |

---

## 六、模型列表速查

| 外部模型名 | 类型 | 说明 |
|-----------|------|------|
| `mm-gemini-2.5-f` | 多模态对话 | Flash 版 |
| `mm-gemini-3.0-p` | 多模态对话 | Pro 版 |
| `mm-gemini-3.1-f` | 多模态对话 | Flash 版 |
| `mm-imagen2` | 图片生成 | 文生图 / 图生图（canvas-20） |
| `mm-h3` | 视频生成 V2 | H3 多模态输入、2K、4~15 秒 |
| `mm-eva-sd-2.0` | 视频生成 | 标准版（国际站） |
| `mm-eva-sd-2.0-fast` | 视频生成 | 快速版（国际站，不支持 1080p） |
| `mm-eva-sd-2.5` | 视频生成 | 2.5 标准版（国际站，收费同 2.0） |
| `mm-eva-sd-2.5-fast` | 视频生成 | 2.5 快速版（国际站，不支持 1080p，收费同 2.0 Fast） |
| `mm-nova-sd-2.0` | 视频生成 | 标准版（国内站） |
| `mm-nova-sd-2.0-fast` | 视频生成 | 快速版（国内站，不支持 1080p） |
| `mm-nova-sd-2.5` | 视频生成 | 2.5 标准版（国内站，收费同 2.0） |
| `mm-nova-sd-2.5-fast` | 视频生成 | 2.5 快速版（国内站，不支持 1080p，收费同 2.0 Fast） |
| `mm-2.8-hd` | 语音合成 | HD，`$100 / 1M` 计费字符 |
| `mm-2.8-turbo` | 语音合成 | Turbo，`$60 / 1M` 计费字符 |
| `mm-2.6-hd` | 语音合成 | HD，`$100 / 1M` 计费字符 |
| `mm-2.6-turbo` | 语音合成 | Turbo，`$60 / 1M` 计费字符 |
| `mm-02-hd` | 语音合成 | HD，`$100 / 1M` 计费字符 |
| `mm-02-turbo` | 语音合成 | Turbo，`$60 / 1M` 计费字符 |


## 七、素材上传转在线地址

该接口用于上传临时图片或视频到公网上，并返回有效期 24 小时的临时访问地址。


### 接口信息

| 项目 | 值 |
|------|-----|
| URL | `POST /v1/assets/upload` |
| 鉴权 | `Authorization: Bearer <your-key>` |
| Content-Type | `multipart/form-data` |
| 支持类型 | 图片、视频 |
| URL 有效期 | 24 小时 |


### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `file` | File | **是** | 要上传的图片或视频文件 |

### Apifox 调用配置

请求地址：

```text
POST http://llm-gw.videoplus.cc/v1/assets/upload
```

请求头：

```http
Authorization: Bearer <your-key>
```

请求体选择：

```text
Body → form-data
```

增加字段：

| 参数名 | 类型 | 参数值 |
|------|------|------|
| `file` | File | 选择本地图片或视频文件 |

> 不要把本地文件路径作为 Text 字符串提交。`file` 参数类型必须选择 `File`，`Content-Type` 由 Apifox 自动生成。

### 支持的文件类型

图片：

- `image/jpeg`
- `image/png`
- `image/webp`
- `image/gif`

视频：

- `video/mp4`
- `video/quicktime`
- `video/webm`

### 文件大小限制

| 文件类型 | 最大大小 |
|------|------:|
| 图片 | 20 MB |
| 视频 | 500 MB |

### curl 请求示例

```bash
curl -X POST 'http://llm-gw.videoplus.cc/v1/assets/upload' \\
  -H 'Authorization: Bearer <your-key>' \\
  -F 'file=@/path/to/demo.mp4'
```

Windows PowerShell：

```powershell
curl.exe -X POST 'http://llm-gw.videoplus.cc/v1/assets/upload' `
  -H 'Authorization: Bearer <your-key>' `
  -F 'file=@C:\Users\admin\Downloads\demo.mp4'
```

### 成功响应

```json
{
  "success": true,
  "file_name": "demo.mp4",
  "asset_type": "video",
  "content_type": "video/mp4",
  "size": 5242880,
  "url": "https://vp-cgir-editor-prod-1389046289.cos.ap-shanghai.myqcloud.com/temporary-assets/20261016/a22a9a7484b144cda16a620f28db532f/demo.mp4?...",
  "expires_in": 86400,
  "expires_at": "2026-10-17T08:00:00Z"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否上传成功 |
| `file_name` | string | 文件名 |
| `asset_type` | string | 文件类型：`image` 或 `video` |
| `content_type` | string | 文件 MIME 类型 |
| `size` | int | 文件大小，单位为字节 |
| `url` | string | COS 临时签名访问地址 |
| `expires_in` | int | URL 有效秒数，默认 `86400` |
| `expires_at` | string | URL 到期时间，ISO 8601 格式 |

### 注意事项

- 该接口只负责上传文件到公共网。
- 文件类型根据上传请求的 MIME 类型判断。
- 返回的签名 URL 有效期为 24 小时，过期后无法继续访问。
- 文件是否在 24 小时后自动删除。
---

## 八、mm 官方素材库（Asset Library）

通过网关代理 mm 官方素材库 API，可注册外部图片/视频/音频 URL 到 mm 素材库并获得素材 ID。

> **说明**：本网关已有自建本地素材库 `[assets-api.md](assets-api.md)`，官方素材库作为补充渠道。

### 接口信息

| 项目 | 值 |
|------|-----|
| URL 前缀 | `/v1/mm/assets` |
| 鉴权 | `Authorization: Bearer <your-key>` |
| Content-Type | `application/json` |

### 注册素材：POST /v1/mm/assets

```http
POST http://llm-gw.videoplus.cc/v1/mm/assets
Authorization: Bearer <your-key>
Content-Type: application/json
```

#### Body 参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `URL` | string | **是** | 公网可访问的图片/视频/音频地址 |
| `AssetType` | string | **是** | `Image` / `Video` / `Audio`（区分大小写） |
| `Name` | string | 否 | 素材名称，支持模糊搜索 |
| `ProjectName` | string | **是** | `eva` 或 `nova`，**两个项目素材库隔离，审核策略不同** |

#### 请求示例

```json
{
  "URL": "https://example.com/ref-image.jpg",
  "AssetType": "Image",
  "Name": "参考图",
  "ProjectName": "eva"
}
```

#### 响应示例

```json
{
  "Id": "asset-20260724120000-a1b2c",
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  }
}
```

---

### 查询素材详情：POST /v1/mm/assets/get

返回素材详情及**签名下载 URL（有效期 12 小时）**。

```http
POST http://llm-gw.videoplus.cc/v1/mm/assets/get
Authorization: Bearer <your-key>
Content-Type: application/json
```

#### Body 参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `Id` | string | **是** | 注册素材时返回的 `Id`（格式 `asset-YYYYMMDDHHMMSS-xxxxx`） |

#### 请求示例

```json
{
  "Id": "asset-20260724120000-a1b2c"
}
```

#### 响应示例

```json
{
  "Id": "asset-20260724120000-a1b2c",
  "GroupId": "group-default",
  "Status": "Active",
  "AssetType": "Image",
  "Name": "参考图",
  "URL": "https://ark-acg.tos-cn-beijing.volces.com/...?X-Tos-Expires=43200&X-Tos-Signature=...",
  "CreateTime": "2026-07-24T04:00:00Z",
  "UpdateTime": "2026-07-24T04:00:00Z",
  "ProjectName": "default",
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  }
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| `Id` | string | 素材 ID |
| `Status` | string | 素材状态：`Active` / `Processing` / `Failed` |
| `AssetType` | string | 素材类型 |
| `URL` | string | **签名下载 URL，有效期 12 小时**。过期后重新调用本接口获取 |
| `CreateTime` | string | 创建时间（ISO 8601） |

---

### 典型用法：注册素材 → 传入视频生成

```text
1. POST /v1/mm/assets → 注册图片/视频/音频，得到 asset-xxx ID
2. POST /v1/mm/assets/get → 获取签名 URL
3. POST /v1/chat/completions → 将签名 URL 作为 reference_image / reference_video / reference_audio 传入
```

```bash
# 1. 注册素材
curl -X POST 'http://llm-gw.videoplus.cc/v1/mm/assets' \
  -H 'Authorization: Bearer <your-key>' \
  -H 'Content-Type: application/json' \
  -d '{
    "URL": "https://example.com/ref.jpg",
    "AssetType": "Image",
    "ProjectName": "eva"
  }'

# 2. 查询签名 URL
curl -X POST 'http://llm-gw.videoplus.cc/v1/mm/assets/get' \
  -H 'Authorization: Bearer <your-key>' \
  -H 'Content-Type: application/json' \
  -d '{"Id": "asset-20260724120000-a1b2c"}'

# 3. 用签名 URL 做视频生成
curl -X POST 'http://llm-gw.videoplus.cc/v1/chat/completions' \
  -H 'Authorization: Bearer <your-key>' \
  -H 'Content-Type: application/json' \
  -H 'X-Biz-Id: op' \
  -d '{
    "model": "mm-nova-sd-2.0",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "根据参考图生成视频"},
        {"type": "image_url", "image_url": {"url": "asset://asset-20260724134753-fmbxw"}, "role": "reference_image"}
      ]
    }]
  }'
```

### 费用说明

素材注册和查询**本身不收费**，费用体现在后续视频/图片生成调用中。

