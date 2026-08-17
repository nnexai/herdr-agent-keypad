/**
 * ComboButton - 组合键示例
 *
 * 演示：同时按下 Button A + Button B 触发组合键事件
 *
 * 接线：
 *   Button A → GPIO 0  → GND
 *   Button B → GPIO 17 → GND
 *   Serial Monitor 波特率 115200
 *
 * 组合键掩码计算（bit 对应 manager.add 顺序）：
 *   btnA        = 0b01 = 0x01
 *   btnB        = 0b10 = 0x02
 *   btnA + btnB = 0b11 = 0x03
 */

#include <ButtonSense.h>
#include <ButtonManager.h>

button::ButtonSense btnA;
button::ButtonSense btnB;

button::ButtonManager manager;

// 组合键位掩码
const uint8_t COMBO_AB = 0x03;  // btnA + btnB

// 组合键回调
void onComboAB(uint8_t mask)
{
    Serial.println("组合键 A+B 触发！");
}

// 普通按键回调
void onButton(button::ButtonSense& b, button::ButtonSense::Event e)
{
    if (e == button::ButtonSense::EVENT_SINGLE_CLICKED)
    {
        Serial.print("按键 GPIO");
        Serial.print(b.getPin());
        Serial.println(": 单击");
    }
    if (e == button::ButtonSense::EVENT_HOLD)
    {
        Serial.print("按键 GPIO");
        Serial.print(b.getPin());
        Serial.println(": 长按");
    }
}

void setup()
{
    Serial.begin(115200);
    delay(500);
    Serial.println("=== ButtonSense - 组合键示例 ===");
    Serial.println("试试同时按下 A+B 组合键...");

    btnA.begin(0);
    btnB.begin(17);

    btnA.onEvent(onButton);
    btnB.onEvent(onButton);

    manager.add(btnA);
    manager.add(btnB);

    // 注册组合键
    manager.onCombo(COMBO_AB, onComboAB);
}

void loop()
{
    manager.update();

    // 也可以通过轮询方式检测组合键
    if (manager.wasComboPressed(COMBO_AB))
    {
        // 组合键刚按下（轮询方式）
    }
}
