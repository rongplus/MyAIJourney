from voxcpm import VoxCPM
import soundfile as sf
import datetime

model = VoxCPM.from_pretrained(
  "openbmb/VoxCPM2",
  load_denoiser=False,
)

texts = [
    "如果你还在死磕‘有氧必须超过30分钟才减脂’，那你可能正在为自己的懒惰找借口，或者，正在无效焦虑。",
    "这个流传甚广的谣言说：前30分钟消耗的是糖，30分钟之后才轮到脂肪。大错特错！事实是：从你开始运动的第一秒，脂肪就在燃烧了！人体的三大供能物质——糖、脂肪、蛋白质，从来不是‘排队上场’，而是‘混合双打’。",
    "科学的真相是：供能比例在动态变化。在运动的前30分钟，糖的供能占比确实大于脂肪，但脂肪依然在贡献能量。而到了30分钟后，糖储备下降，脂肪供能比例反超糖，脂肪燃烧的效率达到峰值。注意听重点：30分钟不是‘起跑线’，而是‘加速带’。 你跑了20分钟，消耗了脂肪；你跑了40分钟，只是消耗了更多的脂肪而已。",
    "所以，少于30分钟就是无效运动？这绝对是谬论！哪怕你只爬了10分钟楼梯、快走了15分钟去地铁站，这20分钟不仅消耗了热量，还激活了你的新陈代谢，避免了久坐带来的血栓风险。动起来，就比坐着强一万倍！",
    "最后送大家一句话：不要因为无法坚持30分钟，就放弃前10分钟的努力。如果你今天很累，那就下楼走15分钟，那是给身体充电；如果你精力充沛，那就坚持40分钟，那是给脂肪加速。我是你的健康顾问，关注我，听点科学的，别被谣言骗了。明天见！"



]
import time

start_time = time.perf_counter()

for i, text in enumerate(texts):
    wav = model.generate(
        text=text,
        cfg_value=2.0,
        inference_timesteps=10,
        reference_wav_path="sample.m4a",
        normalize=True,
    )
    sf.write(f"demo_{i}.wav", wav, model.tts_model.sample_rate)  
    end_time = time.perf_counter()
    run_time = end_time - start_time
    print(f"运行时间: {run_time:.6f} 秒")


print("saved: demo_0.wav, demo_1.wav, demo_2.wav, demo_3.wav, demo_4.wav")
end_time = time.perf_counter()
run_time = end_time - start_time
print(f"运行时间: {run_time:.6f} 秒")

"""
wav = model.generate(
    text="“这个流传甚广的谣言说：前30分钟消耗的是糖，30分钟之后才轮到脂肪。"
    "大错特错！事实是：从你开始运动的第一秒，脂肪就在燃烧了！人体的三大供能物质——糖、脂肪、蛋白质，从来不是‘排队上场’，而是‘混合双打’。”",
    cfg_value=2.0,
    inference_timesteps=10,
    reference_wav_path="sample.m4a",
    normalize=True,
)
sf.write("dem555.wav", wav, model.tts_model.sample_rate)

print("saved: demo5.wav")
"""
