/**
 * SingleButton - 单按键基础示例
 *
 * 演示：单击、双击、三连击、长按、长按重复、长按后释放
 *
 * 接线：
 *   按键一端接 GPIO 0，另一端接 GND（使用内部上拉）
 *   Serial Monitor 波特率 115200
 */

#include <ButtonSense.h>

button::ButtonSense btn;  // GPIO 0，低电平有效，使用内部上拉

void onButtonEvent(button::ButtonSense& b, button::ButtonSense::Event e)
{
    switch (e)
    {
    case button::ButtonSense::EVENT_PRESSED:
        Serial.println("[EVENT] 按下");
        break;

    case button::ButtonSense::EVENT_CLICKED:
        Serial.println("[EVENT] 短按点击");
        break;

    case button::ButtonSense::EVENT_HOLD:
        Serial.println("[EVENT] 开始长按");
        break;

    case button::ButtonSense::EVENT_HOLD_REPEAT:
        Serial.print("[EVENT] 长按重复... 已按住 ");
        Serial.print(b.getLastChangeMs());
        Serial.println(" ms");
        break;

    case button::ButtonSense::EVENT_RELEASED_AFTER_HOLD:
        Serial.println("[EVENT] 长按后释放");
        break;

    case button::ButtonSense::EVENT_SINGLE_CLICKED:
        Serial.println("[EVENT] ★ 单击确定");
        break;

    case button::ButtonSense::EVENT_DOUBLE_CLICKED:
        Serial.println("[EVENT] ★ 双击确定");
        break;

    case button::ButtonSense::EVENT_MULTI_CLICKED:
        Serial.print("[EVENT] ★ ");
        Serial.print(b.getClickCount());
        Serial.println(" 连击确定");
        break;

    default:
        break;
    }
}

void setup()
{
    Serial.begin(115200);
    delay(500);
    Serial.println("=== ButtonSense - 单按键示例 ===");
    Serial.println("试试：短按、双击、长按...");

    btn.begin(0);  // 初始化 GPIO 0
    // btn.onEvent(onButtonEvent);
    // 可选配置
    // btn.setHoldMs(800);          // 长按判定 800ms
    // btn.setHoldRepeatMs(300);    // 长按重复间隔 300ms
    // btn.setDebounceMs(20);       // 去抖 20ms
}

void loop()
{
    btn.update();
}
