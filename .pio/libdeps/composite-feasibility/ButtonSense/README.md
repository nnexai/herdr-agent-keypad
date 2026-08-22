# ButtonSense

一个轻量级的 Arduino 按键驱动库，基于状态机实现去抖、单击、连击、长按及组合键等丰富的按键事件检测。

## 功能特性

| 功能 | 说明 |
|------|------|
| **去抖** | 可配置去抖时间（默认 10ms） |
| **短按/单击** | 按下后快速释放 |
| **双击/连击** | 可配置连击超时窗口，支持任意次数连击 |
| **长按** | 按住超过阈值触发（默认 500ms） |
| **长按重复** | 按住期间周期性触发（如音量调节） |
| **长按后释放** | 长按松手时的事件通知 |
| **回调机制** | 所有事件通过回调函数异步通知 |
| **多按键管理** | `ButtonManager` 统一管理多个按键 |
| **组合键检测** | 同时按下多个按键的组合检测 |

## 事件类型

```cpp
EVENT_NONE              // 无事件
EVENT_PRESSED           // 刚按下
EVENT_RELEASED          // 刚释放
EVENT_CLICKED           // 短按点击
EVENT_HOLD              // 长按开始
EVENT_HOLD_REPEAT       // 长按重复触发
EVENT_SINGLE_CLICKED    // 单击确定（连击窗口结束）
EVENT_DOUBLE_CLICKED    // 双击确定
EVENT_MULTI_CLICKED     // 连击确定（配合 getClickCount()）
EVENT_RELEASED_AFTER_HOLD // 长按后释放
```

## 快速开始

### 单按键

```cpp
#include <ButtonSense.h>

button::ButtonSense btn;

void onButton(button::ButtonSense& b, button::ButtonSense::Event e)
{
    if (e == button::ButtonSense::EVENT_SINGLE_CLICKED)
        Serial.println("Button clicked!");
}

void setup()
{
    Serial.begin(115200);
    btn.begin(0);  // GPIO 0
    btn.onEvent(onButton);
}

void loop()
{
    btn.update();
}
```

### 多按键 + 组合键

```cpp
#include <ButtonSense.h>
#include <ButtonManager.h>

button::ButtonSense btnA;
button::ButtonSense btnB;
button::ButtonManager manager;

void onComboAB(uint8_t mask)
{
    Serial.println("Combo A+B pressed!");
}

void setup()
{
    btnA.begin(0);
    btnB.begin(17);
    manager.add(btnA);
    manager.add(btnB);
    manager.onCombo(0x03, onComboAB);  // bit0+bit1
}

void loop()
{
    manager.update();
}
```

## 配置参数

| 方法 | 默认值 | 说明 |
|------|--------|------|
| `setDebounceThresh(ms)` | 10 | 去抖时间 |
| `setHoldThresh(ms)` | 500 | 长按判定阈值 |
| `setHoldRepeatMs(ms)` | 200 | 长按重复间隔（0=禁用） |
| `setMultiClickTimeoutMs(ms)` | =holdMs | 连击判定窗口 |

## 许可证

MIT License
