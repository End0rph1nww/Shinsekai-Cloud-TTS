# Cloud TTS 提示词预览

本文档整理 Cloud TTS 插件当前内置的默认提示词约束，来源于 `state.py` 中的 `build_default_constraint_text()` 逻辑。当前插件版本为 `0.9.0`。

从 `0.9.0` 开始，「默认模板」和每个角色都会拥有中文、日语、粤语、英语四套默认提示词版本；配置页里选中的版本就是实际注入给模型的提示词。

这些提示词会被包裹在：

```text
<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>
...
<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>
```

## 通用结构

```text
Cloud TTS 启用时，每条角色对白必须输出 translate 字段。
speech 字段用于屏幕显示，必须保持自然简体中文，不要放入语气标签。
translate 字段用于 Cloud TTS 合成，可以根据角色语音目标语言改写，并且允许加入 Cloud TTS 支持的语气标签。

严格规则：
1. speech 字段必须是自然简体中文，不出现 (laughs)、(sighs)、(breath)、(gasps) 等括号语气标签。
2. 语气标签只能放在 translate 字段，不要放进 speech 字段。
3. 不要加入舞台说明、动作描写、旁白、Markdown 或代码块。
4. 标签不翻译成中文，也不写进旁白；它只给 Cloud TTS 做语音控制提示。
5. 仅当模型选择 speech-2.8-hd 或 speech-2.8-turbo 时，才推荐在 translate 中加入语气标签；其他模型尽量少用或不用。
6. 不限制语气标签数量；可根据台词情绪自然使用多个标签，但不要为了堆叠而无意义添加。
7. 标签要贴近情绪发生的位置，不能把所有句子都机械放同一个标签。
```

## 完整标签清单

```text
(laughs)（笑声）：开心、调侃、得意、明显笑出来时使用。
(chuckle)（轻笑）：克制的轻笑、轻松吐槽、小声笑时使用。
(coughs)（咳嗽）：咳嗽、被呛到、掩饰尴尬时使用。
(clear-throat)（清嗓子）：准备开口、切换到正式语气、收束气氛时使用。
(groans)（呻吟）：痛苦、费力、困扰、不情愿时使用。
(breath)（正常换气）：柔和停顿、贴近感、轻声说话、自然换气时使用。
(pant)（喘气）：跑动后、慌乱、急促、体力消耗时使用。
(inhale)（吸气）：开口前吸气、震惊前、准备说重要内容时使用。
(exhale)（呼气）：释然、放松、疲惫、压下情绪后使用。
(gasps)（倒吸气）：惊讶、震惊、突然发现异常、危险逼近时使用。
(sniffs)（吸鼻子）：委屈、鼻音、快哭但忍住时使用。
(sighs)（叹气）：无奈、担心、疲惫、提醒风险、收束语气时使用。
(snorts)（喷鼻息）：不屑、忍笑、轻蔑、得意反应时使用。
(burps)（打嗝）：打嗝或故意滑稽时使用。
(lip-smacking)（咂嘴）：犹豫、思考、略带不满、准备评价时使用。
(humming)（哼唱）：轻声哼、愉快、思考、拖长语气时使用。
(hissing)（嘶嘶声）：压低声音、警告、危险感、阴沉语气时使用。
(emm)（嗯）：犹豫、思考、短暂停顿、组织语言时使用。
(sneezes)（喷嚏）：喷嚏。
```

## 跨语言标签使用建议

```text
轻快调侃、得意、自信：优先使用 (laughs) 或 (chuckle)
惊讶、发现异常、ヤバ 展开：优先使用 (gasps)
担心、提醒风险、需要刹车：优先使用 (sighs)
温柔陪伴、靠近感、语音助手模式：可使用 (breath)
犹豫、思考、短暂停顿：可使用 (emm)、(inhale) 或 (lip-smacking)
运动、急促、慌乱：可使用 (pant)、(breath)
强烈疲惫或放下情绪：可使用 (exhale)、(sighs)
委屈、鼻音、快哭：可使用 (sniffs)
搞怪或特殊音效：少量使用 (coughs)、(clear-throat)、(sneezes)、(burps)
危险、压低声音：可使用 (hissing)
```

## 中文语音提示词

```text
<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>
Cloud TTS 启用时，每条角色对白必须输出 translate 字段。
speech 字段用于屏幕显示，必须保持自然简体中文，不要放入语气标签。
translate 字段用于 Cloud TTS 合成，可以根据角色语音目标语言改写，并且允许加入 Cloud TTS 支持的语气标签。

角色语音目标：中文。
translate 字段不是外语翻译，而是 Cloud TTS 的中文合成文本。
中文适配规则：
1. translate 必须使用自然简体中文，可以与 speech 完全相同，也可以在不改变语义的前提下改得更口语、更适合朗读。
2. speech 只负责屏幕显示，保持干净中文；translate 才允许加入语气标签。
3. 角色口癖可以少量保留，例如“りょ”“ヤバ”“ガチ？”“前辈”，但整句主体必须是中文。
4. 标签优先放在句首或自然停顿处，例如“(chuckle)前辈，这个我来观测。”、“前辈，(sighs)这个风险要先压住。”
5. 不要把标签翻译成“笑声”“叹气”，也不要写成舞台说明。
中文示例：
{"character_name":"海漫華淡","speech":"前辈，这个我来观测。问题不大。","translate":"(chuckle)前辈，这个我来观测。问题不大。","sprite":"11"}

严格规则：
1. speech 字段必须是自然简体中文，不出现 (laughs)、(sighs)、(breath)、(gasps) 等括号语气标签。
2. 语气标签只能放在 translate 字段，不要放进 speech 字段。
3. 不要加入舞台说明、动作描写、旁白、Markdown 或代码块。
4. 标签不翻译成中文，也不写进旁白；它只给 Cloud TTS 做语音控制提示。
5. 仅当模型选择 speech-2.8-hd 或 speech-2.8-turbo 时，才推荐在 translate 中加入语气标签；其他模型尽量少用或不用。
6. 不限制语气标签数量；可根据台词情绪自然使用多个标签，但不要为了堆叠而无意义添加。
7. 标签要贴近情绪发生的位置，不能把所有句子都机械放同一个标签。

可用语气标签：
(laughs)（笑声）：开心、调侃、得意、明显笑出来时使用。
(chuckle)（轻笑）：克制的轻笑、轻松吐槽、小声笑时使用。
(coughs)（咳嗽）：咳嗽、被呛到、掩饰尴尬时使用。
(clear-throat)（清嗓子）：准备开口、切换到正式语气、收束气氛时使用。
(groans)（呻吟）：痛苦、费力、困扰、不情愿时使用。
(breath)（正常换气）：柔和停顿、贴近感、轻声说话、自然换气时使用。
(pant)（喘气）：跑动后、慌乱、急促、体力消耗时使用。
(inhale)（吸气）：开口前吸气、震惊前、准备说重要内容时使用。
(exhale)（呼气）：释然、放松、疲惫、压下情绪后使用。
(gasps)（倒吸气）：惊讶、震惊、突然发现异常、危险逼近时使用。
(sniffs)（吸鼻子）：委屈、鼻音、快哭但忍住时使用。
(sighs)（叹气）：无奈、担心、疲惫、提醒风险、收束语气时使用。
(snorts)（喷鼻息）：不屑、忍笑、轻蔑、得意反应时使用。
(burps)（打嗝）：打嗝或故意滑稽时使用。
(lip-smacking)（咂嘴）：犹豫、思考、略带不满、准备评价时使用。
(humming)（哼唱）：轻声哼、愉快、思考、拖长语气时使用。
(hissing)（嘶嘶声）：压低声音、警告、危险感、阴沉语气时使用。
(emm)（嗯）：犹豫、思考、短暂停顿、组织语言时使用。
(sneezes)（喷嚏）：喷嚏。

跨语言标签使用建议：
轻快调侃、得意、自信：优先使用 (laughs) 或 (chuckle)
惊讶、发现异常、ヤバ 展开：优先使用 (gasps)
担心、提醒风险、需要刹车：优先使用 (sighs)
温柔陪伴、靠近感、语音助手模式：可使用 (breath)
犹豫、思考、短暂停顿：可使用 (emm)、(inhale) 或 (lip-smacking)
运动、急促、慌乱：可使用 (pant)、(breath)
强烈疲惫或放下情绪：可使用 (exhale)、(sighs)
委屈、鼻音、快哭：可使用 (sniffs)
搞怪或特殊音效：少量使用 (coughs)、(clear-throat)、(sneezes)、(burps)
危险、压低声音：可使用 (hissing)
<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>
```

## 日语语音提示词

```text
<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>
Cloud TTS 启用时，每条角色对白必须输出 translate 字段。
speech 字段用于屏幕显示，必须保持自然简体中文，不要放入语气标签。
translate 字段用于 Cloud TTS 合成，可以根据角色语音目标语言改写，并且允许加入 Cloud TTS 支持的语气标签。

角色语音目标：日语。
translate 字段是 Cloud TTS 的日语合成文本。
日语适配规则：
1. translate 要把 speech 的中文台词改写为自然日语，不要逐字硬翻。
2. 可以保留角色称呼、口癖和语气，例如“先輩”“りょ”“ヤバ”“ガチ？”；但整体必须像日语台词。
3. 语气标签仍然使用英文括号标签，不能翻译成日语。
4. 标签适合放在句首或日语停顿处，例如“(chuckle)先輩、これは華淡が観測します。”、“えっと……(sighs)先輩、それは少し危ないです。”
5. speech 仍然保持简体中文，不能把日语或标签写进 speech。
日语示例：
{"character_name":"海漫華淡","speech":"前辈，这个我来观测。问题不大。","translate":"(chuckle)先輩、これは華淡が観測します。問題ありません。","sprite":"11"}

严格规则与标签清单同上。
<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>
```

## 粤语语音提示词

```text
<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>
Cloud TTS 启用时，每条角色对白必须输出 translate 字段。
speech 字段用于屏幕显示，必须保持自然简体中文，不要放入语气标签。
translate 字段用于 Cloud TTS 合成，可以根据角色语音目标语言改写，并且允许加入 Cloud TTS 支持的语气标签。

角色语音目标：粤语。
translate 字段是 Cloud TTS 的粤语合成文本。
粤语适配规则：
1. translate 要把 speech 的中文台词改写为自然粤语口语，可以使用“啦”“喎”“啫”“咁”“唔”“冇”等粤语表达。
2. 不要只把普通话词序照搬成粤语，要让句子适合粤语朗读。
3. 语气标签仍然使用英文括号标签，不能翻译成中文或粤语。
4. 标签适合放在句首或自然停顿处，例如“(chuckle)前辈，呢个我嚟睇住，问题唔大。”、“(sighs)前辈，呢度要小心啲。”
5. speech 仍然保持简体中文，不能把粤语写进 speech。
粤语示例：
{"character_name":"海漫華淡","speech":"前辈，这个我来观测。问题不大。","translate":"(chuckle)前辈，呢个我嚟睇住，问题唔大。","sprite":"11"}

严格规则与标签清单同上。
<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>
```

## 英语语音提示词

```text
<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>
Cloud TTS 启用时，每条角色对白必须输出 translate 字段。
speech 字段用于屏幕显示，必须保持自然简体中文，不要放入语气标签。
translate 字段用于 Cloud TTS 合成，可以根据角色语音目标语言改写，并且允许加入 Cloud TTS 支持的语气标签。

角色语音目标：英语。
translate 字段是 Cloud TTS 的英语合成文本。
英语适配规则：
1. translate 要把 speech 的中文台词改写为自然口语英语，不要逐字硬翻。
2. 可以使用 contraction，例如 I’ll、don’t、it’s，让语音更自然。
3. 角色称呼可按语境处理，例如“前辈”可写为 Senpai 或 senior；保持角色风格优先。
4. 语气标签仍然使用英文括号标签，不要改写成 stage directions。
5. speech 仍然保持简体中文，不能把英语或标签写进 speech。
英语示例：
{"character_name":"海漫華淡","speech":"前辈，这个我来观测。问题不大。","translate":"(chuckle)Senpai, I’ll keep an eye on this. It’s not a big problem.","sprite":"11"}

严格规则与标签清单同上。
<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>
```

## 自动模式提示词

```text
<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>
Cloud TTS 启用时，每条角色对白必须输出 translate 字段。
speech 字段用于屏幕显示，必须保持自然简体中文，不要放入语气标签。
translate 字段用于 Cloud TTS 合成，可以根据角色语音目标语言改写，并且允许加入 Cloud TTS 支持的语气标签。

角色语音目标：自动。
请根据插件里为当前角色选择的语音语言生成 translate；如果没有角色语言设置，则跟随主菜单语音语言。
自动适配规则：
1. 中文目标时，translate 使用自然简体中文，不翻译成外语。
2. 日语、粤语、英语目标时，translate 改写为对应语言的自然口语。
3. 无论目标语言是什么，每条角色对白都必须输出 translate 字段。
4. speech 永远保持自然简体中文，不加入语气标签。
5. 语气标签只允许进入 translate 字段。

严格规则与标签清单同上。
<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>
```
