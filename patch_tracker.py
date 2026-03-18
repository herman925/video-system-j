import re

content = open('tracker/page.py', encoding='utf-8').read()

# find _score_info definition
start_idx = content.find('def _score_info(score')
end_idx = content.find('def _score_html(rating')

if start_idx != -1 and end_idx != -1:
    extracted = content[start_idx:end_idx]
    
    # We replace it with nothing, and add the import to the top
    new_content = content[:start_idx] + content[end_idx:]
    
    # add import at the top
    if 'from utils.ui_ratings import get_score_info' not in new_content:
        new_content = new_content.replace('from utils.ui_ratings import', 'from utils.ui_ratings import get_score_info as _score_info,\n    ')
        
    open('tracker/page.py', 'w', encoding='utf-8').write(new_content)
    
    # Now let's extract the _span tips to a dictionary for ui_ratings.py
    tips = {}
    
    # extract Onyx and Low rank manually
    # Onyx
    onyx_match = re.search(r'<span title=\"(.*?Onyx.*?)\"', extracted, re.DOTALL)
    if onyx_match: tips['onyx'] = onyx_match.group(1)
    
    # others
    for m in re.findall(r'_span\(\s*\"(.*?)\"\s*,', extracted, re.DOTALL):
        if 'Diamond' in m: tips['diamond'] = m
        elif 'Ruby' in m: tips['ruby'] = m
        elif 'Sapphire' in m: tips['sapphire'] = m
        elif 'Amethyst' in m: tips['amethyst'] = m
        elif 'Emerald' in m: tips['emerald'] = m
        elif 'Gold' in m: tips['gold'] = m
        elif 'Topaz' in m: tips['topaz'] = m
        elif 'Silver' in m: tips['silver'] = m
        elif 'Aquamarine' in m: tips['aquamarine'] = m
        elif 'Jade' in m: tips['jade'] = m
        elif 'Garnet' in m: tips['garnet'] = m

    import json
    open('default_tips.json', 'w', encoding='utf-8').write(json.dumps(tips, indent=2))
    print("Patched tracker/page.py")
