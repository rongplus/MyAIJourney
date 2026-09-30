from voxcpm import VoxCPM
import soundfile as sf
import datetime

model = VoxCPM.from_pretrained(
  "openbmb/VoxCPM2",
  load_denoiser=False,
)

texts = [
    "If you're still obsessing over the idea that 'cardio must exceed 30 minutes to burn fat,' you might be making excuses for your laziness—or pointlessly stressing out.",
    "This widely spread myth says: the first 30 minutes burn sugar, and only after 30 minutes does fat get its turn. Completely wrong! The truth is: from the very first second you start exercising, fat is already burning! The body's three energy sources—sugar, fat, and protein—never 'line up in turn'; they work in 'mixed doubles' mode.",
    "The scientific reality is: energy contribution ratios shift dynamically. During the first 30 minutes of exercise, sugar does contribute more than fat, but fat is still supplying energy. After 30 minutes, as sugar reserves drop, fat's contribution overtakes sugar, and fat-burning efficiency peaks. Pay attention to the key point: 30 minutes isn't a 'starting line'—it's an 'acceleration zone.' Running 20 minutes burns fat; running 40 minutes simply burns more fat.",
    "So is less than 30 minutes of exercise pointless? That's absolutely a fallacy! Even if you only climbed stairs for 10 minutes or brisk-walked 15 minutes to the subway station, those 20 minutes not only burned calories but also activated your metabolism, reducing the risk of blood clots from prolonged sitting. Moving at all is ten thousand times better than sitting still!",
    "One last piece of advice: don't give up on the first 10 minutes of effort just because you can't sustain 30 minutes. If you're tired today, go walk for 15 minutes—that's recharging your body; if you're full of energy, then push for 40 minutes—that's accelerating fat loss. I'm your health advisor—follow me for some science, and don't get fooled by myths. See you tomorrow!"
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
    print(f"Runtime: {run_time:.6f} seconds")


print("saved: demo_0.wav, demo_1.wav, demo_2.wav, demo_3.wav, demo_4.wav")
end_time = time.perf_counter()
run_time = end_time - start_time
print(f"Runtime: {run_time:.6f} seconds")

"""
wav = model.generate(
    text="This widely spread myth says: the first 30 minutes burn sugar, "
    "and only after 30 minutes does fat get its turn. Completely wrong! "
    "The truth is: from the very first second you start exercising, fat is already burning! "
    "The body's three energy sources—sugar, fat, and protein—never 'line up in turn'; "
    "they work in 'mixed doubles' mode.",
    cfg_value=2.0,
    inference_timesteps=10,
    reference_wav_path="sample.m4a",
    normalize=True,
)
sf.write("dem555.wav", wav, model.tts_model.sample_rate)

print("saved: demo5.wav")
"""
