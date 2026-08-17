/**
 * MultiButton - 多按键示例
 *
 * 演示：同时管理三个按键，各自独立触发事件
 *
 * 接线：
 *   Button A → GPIO 0  → GND
 *   Button B → GPIO 13 → GND
 *   Button C → GPIO 27 → GND
 *   Serial Monitor 波特率 115200
 */

#include <ButtonSense.h>
#include <ButtonManager.h>

button::ButtonSense btnA;
button::ButtonSense btnB;
button::ButtonSense btnC;

button::ButtonManager manager;

// 按键 A 的回调
void onButtonA(button::ButtonSense& b, button::ButtonSense::Event e)
{
    switch (e) {
        case button::ButtonSense::EVENT_SINGLE_CLICKED:   Serial.println("A: 单击"); break;
        case button::ButtonSense::EVENT_DOUBLE_CLICKED:   Serial.println("A: 双击"); break;
        case button::ButtonSense::EVENT_MULTI_CLICKED:
            Serial.print("A: 连击 "); Serial.print(b.getClickCount()); Serial.println(" 次");
            break;
        case button::ButtonSense::EVENT_HOLD:             Serial.println("A: 长按开始"); break;
        case button::ButtonSense::EVENT_HOLD_REPEAT:      Serial.println("A: 长按重复"); break;
        case button::ButtonSense::EVENT_RELEASED_AFTER_HOLD: Serial.println("A: 长按释放"); break;
        default: break;
    }
}

// 按键 B 的回调
void onButtonB(button::ButtonSense& b, button::ButtonSense::Event e)
{
    switch (e) {
        case button::ButtonSense::EVENT_SINGLE_CLICKED:   Serial.println("B: 单击"); break;
        case button::ButtonSense::EVENT_DOUBLE_CLICKED:   Serial.println("B: 双击"); break;
        case button::ButtonSense::EVENT_MULTI_CLICKED:
            Serial.print("B: 连击 "); Serial.print(b.getClickCount()); Serial.println(" 次");
            break;
        case button::ButtonSense::EVENT_HOLD:             Serial.println("B: 长按开始"); break;
        case button::ButtonSense::EVENT_HOLD_REPEAT:      Serial.println("B: 长按重复"); break;
        case button::ButtonSense::EVENT_RELEASED_AFTER_HOLD: Serial.println("B: 长按释放"); break;
        default: break;
    }
}

void setup()
{
    Serial.begin(115200);
    delay(500);
    Serial.println("=== ButtonSense - 多按键示例 ===");

    btnA.begin(0);
    btnB.begin(17);

    btnA.onEvent(onButtonA);
    btnB.onEvent(onButtonB);

    manager.add(btnA);
    manager.add(btnB);
}

void loop()
{
    manager.update();  // 一键更新所有按键
}
