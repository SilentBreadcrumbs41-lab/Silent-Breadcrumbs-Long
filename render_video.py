import os, sys, json, subprocess, time, random, asyncio, re, string
import urllib.parse
import aiohttp
import edge_tts
import shutil

# --- VARIABLES ---
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'The Unsolved Enigma')
description = os.environ.get('DESCRIPTION', 'Decode the hidden clues behind the worlds most baffling unsolved paradoxes.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic dark foggy mystery landscape, highly detailed')
pexels_key = os.environ.get('PEXELS_API_KEY')
chat_id = os.environ.get('CHAT_ID')
telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')

# 👇 Channel Watermark
channel_name = "Silent Breadcrumbs®" 

print(f"DEBUG: Processing {len(scenes_data)} scenes async...")

# --- SMART DYNAMIC FALLBACK KEYWORDS (Metaphorical Visuals) ---
fallback_env = os.environ.get('FALLBACK_KEYWORDS', 'dark nature, foggy forest path, abandoned architecture, night urban, shadows moving, cinematic dark, macro space nebulas, vintage clockworks, abstract data lines, microscopic cells, deep space stars, geometric abstract shapes')
FALLBACK_KEYWORDS = [kw.strip() for kw in fallback_env.split(',')]

TEMP_DIR = "/dev/shm" if os.path.exists("/dev/shm") else os.getcwd()

async def get_audio_duration(file_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except:
        return 5.0 

async def fetch_pexels_video(session, keyword):
    queries_to_try = [keyword] + FALLBACK_KEYWORDS
    for query in queries_to_try:
        for attempt in range(2):
            try:
                await asyncio.sleep(random.uniform(0.1, 0.5))
                random_page = random.randint(1, 2) if attempt == 0 else 1 
                url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=15&page={random_page}&orientation=landscape"
                
                async with session.get(url, headers={"Authorization": pexels_key}, timeout=10) as response:
                    if response.status == 429:
                        await asyncio.sleep(2)
                        continue
                        
                    if response.status == 200:
                        res = await response.json()
                        videos = res.get('videos', [])
                        if videos:
                            random.shuffle(videos)
                            for v in videos[:3]:
                                try:
                                    vid_url = v['video_files'][0]['link']
                                    for vf in v['video_files']:
                                        if vf.get('quality') == 'hd':
                                            vid_url = vf['link']
                                            break
                                    return vid_url
                                except Exception:
                                    continue
            except Exception:
                continue
    return None

async def process_scene(session, i, scene, total_scenes):
    keyword = scene.get('keyword', 'cinematic dark')
    text_line = scene.get('text', '').strip()
    if not text_line: return None
    
    scene_filename = os.path.join(TEMP_DIR, f"scene_{i}.mp4")
    raw_mp3 = os.path.join(TEMP_DIR, f"raw_a_{i}.mp3")
    vid_path = os.path.join(TEMP_DIR, f"raw_vid_{i}.mp4")
    
    try:
        # --- 1. TTS GENERATION ---
        tts_success = False
        for attempt in range(3):
            try:
                communicate = edge_tts.Communicate(text_line, "en-US-ChristopherNeural")
                await asyncio.wait_for(communicate.save(raw_mp3), timeout=15.0)
                tts_success = True
                break
            except asyncio.TimeoutError:
                print(f"TTS Timeout on attempt {attempt+1} for scene {i}. Retrying...")
            except Exception as e:
                print(f"TTS Attempt {attempt+1} failed for scene {i}: {str(e)}")
                await asyncio.sleep(2)
                
        if not tts_success:
            print(f"Skipping scene {i} due to continuous TTS failure.")
            return None
            
        raw_dur = await get_audio_duration(raw_mp3)
        dur = max(1.0, raw_dur - 0.2) 
        fade_out = max(0, dur - 0.5)
        
        # --- 2. GUARANTEED VIDEO FETCH ---
        is_valid_video = False
        vid_url = await fetch_pexels_video(session, keyword)
        
        for download_attempt in range(3):
            if not vid_url:
                vid_url = await fetch_pexels_video(session, random.choice(FALLBACK_KEYWORDS))
                
            if vid_url:
                try:
                    async with session.get(vid_url, timeout=15) as vid_resp:
                        if vid_resp.status == 200:
                            vid_bytes = await vid_resp.read()
                            # 👇 YAHAN SIZE LIMIT 50KB KAR DI HAI TAAKI PEXELS KE CHHOTE VIDEO BHI CHAL SAKEIN 👇
                            if len(vid_bytes) > 50000:
                                with open(vid_path, "wb") as f:
                                    f.write(vid_bytes)
                                is_valid_video = True
                                break 
                except Exception as e:
                    print(f"Failed to download video for scene {i}: {str(e)}")
            vid_url = None

        # --- 3. VIDEO RENDER (NO CAPTIONS, ONLY CHAPTERS & CTA) ---
        pop_path = os.path.abspath("pop.mp3")
        whoosh_path = os.path.abspath("whoosh.mp3")
        has_pop = os.path.exists(pop_path)
        has_whoosh = os.path.exists(whoosh_path)
        
        is_chapter_scene = (i % 7 == 0 and i != 0)
        chapter_num = (i // 7) + 1
        is_last_scene = (i == total_scenes - 1)

        if is_chapter_scene:
            # Dark screen chapter transition
            chap_text = f",drawtext=text='CHAPTER {chapter_num}':fontcolor=white:fontsize=130:x=(w-tw)/2:y=(h-th)/2:enable='between(t,0,3)'"
            v_fade_in = "fade=t=in:st=0:d=1.0"
            # 👇 YAHAN BRIGHTNESS -0.15 KI HAI TAAKI SCREEN KAALI NA HO 👇
            bg_dim = "eq=contrast=1.0:saturation=0.3:brightness=-0.15" 
        else:
            chap_text = ""
            v_fade_in = "fade=t=in:st=0:d=0.5"
            bg_dim = "eq=contrast=1.2:saturation=0.85"

        # Massive CTA at the end
        if is_last_scene:
            chap_text += f",drawtext=text='SUBSCRIBE FOR MORE':fontcolor=white:fontsize=100:x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=#FF0000@0.9:boxborderw=30:enable='between(t,1.5,15)'"

        wm_text = f",drawtext=text='{channel_name}':fontcolor=white@0.2:fontsize=48:x=w-tw-50:y=h-th-50"
        v_filter_base = f"format=yuv420p,fps=30,setsar=1,{v_fade_in},fade=t=out:st={fade_out}:d=0.5"

        cmd = ['ffmpeg', '-y']
        
        if is_valid_video:
            cmd += ['-ignore_editlist', '1', '-stream_loop', '-1', '-fflags', '+genpts', '-i', vid_path]
            # 👇 YAHAN BASS 'setpts=PTS-STARTPTS,' ADD KIYA HAI VIDEO GAYAB HONE SE ROKNE KE LIYE 👇
            v_filter = f"[0:v]setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,{bg_dim},{v_filter_base}{wm_text}{chap_text}[v]"
        else:
            cmd += ['-f', 'lavfi', '-i', f'color=c=#101015:s=1920x1080:r=30:d={dur}']
            v_filter = f"[0:v]{v_filter_base}{wm_text}{chap_text}[v]"

        cmd += ['-ss', '0.2', '-i', raw_mp3]

        # 👇 YAHAN AUDIO MIXING KO AFORMAT DEKAR FIX KIYA GAYA HAI 👇
        audio_inputs = 1
        a_filter = "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.0[voice];"
        a_mix_labels = "[voice]"

        if has_pop:
            cmd += ['-i', pop_path]
            pop_idx = audio_inputs + 1
            a_filter += f"[{pop_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.8[pop];"
            a_mix_labels += "[pop]"
            audio_inputs += 1

        if is_chapter_scene and has_whoosh:
            cmd += ['-i', whoosh_path]
            whoosh_idx = audio_inputs + 1
            a_filter += f"[{whoosh_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.0[whoosh];"
            a_mix_labels += "[whoosh]"
            audio_inputs += 1

        if audio_inputs > 1:
            a_filter += f"{a_mix_labels}amix=inputs={audio_inputs}:duration=first:dropout_transition=0[aout_mix];[aout_mix]volume=2.0[aout]"
            a_map = '[aout]'
        else:
            a_filter = ""
            a_map = '1:a'

        if a_filter:
            filter_complex = f"{v_filter};{a_filter}"
        else:
            filter_complex = v_filter
            
        cmd += [
            '-filter_complex', filter_complex,
            '-map', '[v]', '-map', a_map,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-pix_fmt', 'yuv420p',
            '-t', str(dur), scene_filename
        ]
            
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await proc.communicate()
        
        return {"vid": scene_filename, "aud": raw_mp3, "index": i}
        
    except Exception as e: 
        print(f"Error in scene {i}: {str(e)}")
        return None
    finally:
        if os.path.exists(vid_path): os.remove(vid_path)

async def run_ffmpeg_async(cmd):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await proc.communicate()

async def main_pipeline():
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(4)
        
        async def safe_process(session, i, scene, total):
            async with sem:
                return await process_scene(session, i, scene, total)

        total_scenes = len(scenes_data)
        tasks = [safe_process(session, i, scene, total_scenes) for i, scene in enumerate(scenes_data)]
        results = await asyncio.gather(*tasks)
        
        results = sorted([r for r in results if r], key=lambda x: x['index'])

        vid_list_path = os.path.join(TEMP_DIR, "vid_list.txt")
        
        with open(vid_list_path, "w") as f:
            for r in results: f.write(f"file '{r['vid']}'\n")

        raw_video = os.path.join(TEMP_DIR, 'raw_video.mp4')
        final_video = 'final_video.mp4' 
        
        # ==========================================
        # PHASE 2: FLAWLESS AUDIO MUXING
        # ==========================================
        await run_ffmpeg_async(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', vid_list_path, '-c', 'copy', raw_video])

        bgm_path = os.path.abspath("bgm.mp3")
        if os.path.exists(bgm_path):
            bgm_cmd = [
                'ffmpeg', '-y', '-i', raw_video, '-stream_loop', '-1', '-i', bgm_path,
                '-filter_complex', '[0:a]volume=1.0[voice];[1:a]volume=0.25[bgm];[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout_mix];[aout_mix]volume=2.0[aout]',
                '-map', '0:v', '-map', '[aout]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', final_video
            ]
            await run_ffmpeg_async(bgm_cmd)
        else:
            shutil.move(raw_video, final_video)

        # Cleanup
        if os.path.exists(vid_list_path): os.remove(vid_list_path)
        if os.path.exists(raw_video): os.remove(raw_video)
        for r in results:
            if os.path.exists(r['vid']): os.remove(r['vid'])
            if os.path.exists(r['aud']): os.remove(r['aud'])

        # ==========================================
        # PHASE 3: GITHUB RELEASES
        # ==========================================
        video_link = None
        print("\n🚀 Uploading Video directly to GitHub Releases...")
        
        run_id = os.environ.get('GITHUB_RUN_ID', str(int(time.time())))
        tag_name = f"vid-{run_id}"
        # 👇 Repo name updated based on the image
        repo_name = os.environ.get('GITHUB_REPOSITORY', "SilentBreadcrumbs41-lab/Silent-Breadcrumbs-Long") 
        
        try:
            cmd = ['gh', 'release', 'create', tag_name, final_video, '--repo', repo_name, '--notes', 'Automated Video Render']
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                video_link = f"https://github.com/{repo_name}/releases/download/{tag_name}/final_video.mp4"
                print(f"✅ Success! Video uploaded to GitHub: {video_link}")
            else:
                err_msg = stderr.decode().strip()
                print(f"❌ GitHub Release failed. Error: {err_msg}")
        except Exception as e:
            print(f"⚠️ Exception during GitHub upload: {str(e)}")

        # ==========================================
        # PHASE 4: TELEGRAM NOTIFICATION
        # ==========================================
        if telegram_token:
            if video_link:
                payload = {"chat_id": chat_id, "text": f"READY_TO_UPLOAD|{video_link}|{title.replace('|', '')}|{thumbnail_prompt.replace('|', '')}|{description.replace('|', '')}"}
            else:
                payload = {"chat_id": chat_id, "text": f"⚠️ ERROR: Upload fail hua. GitHub release banne mein problem aayi."}
            
            try:
                async with session.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", json=payload) as resp:
                    resp_text = await resp.text()
                    print(f"\n--- TELEGRAM DEBUG ---")
                    print(f"Status Code: {resp.status}")
                    print(f"Response: {resp_text}")
                    print(f"----------------------\n")
            except Exception as e:
                print(f"CRITICAL: Telegram API error - {str(e)}")
        else:
            print("CRITICAL WARNING: Telegram token missing. Cannot send notification.")

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_pipeline())
