# Gap Filler for price_data.json (gap_filler.py)
#
# This script reads price_data.json, detects gaps larger than specified threshold,
# fills them with interpolated points, and saves the result to price_data_fix.json
#
# Usage: python gap_filler.py

import json
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# --- Configuration ---
INPUT_FILE = "price_data.json"
OUTPUT_FILE = "price_data_fix.json"
MAX_GAP_SECONDS = 120  # Fill gaps larger than 2 minutes (120 seconds)
INTERPOLATION_INTERVAL_SECONDS = 60  # Create points every 60 seconds in gaps
ADD_RANDOM_VARIATION = True  # Add small random price variation to interpolated points
RANDOM_VARIATION_PERCENT = 0.001  # ±0.1% random variation

def detect_gaps(data, max_gap_seconds=MAX_GAP_SECONDS):
    """Detect gaps in price data that need filling"""
    gaps = []
    
    if len(data) < 2:
        return gaps
    
    print(f"🔍 Scanning {len(data)} records for gaps larger than {max_gap_seconds} seconds...")
    
    for i in range(1, len(data)):
        current_time = pd.to_datetime(data[i]['timestamp'])
        prev_time = pd.to_datetime(data[i-1]['timestamp'])
        
        time_diff_seconds = (current_time - prev_time).total_seconds()
        
        if time_diff_seconds > max_gap_seconds:
            gaps.append({
                'index': i,
                'start_time': prev_time,
                'end_time': current_time,
                'duration_seconds': time_diff_seconds,
                'start_price': data[i-1]['price'],
                'end_price': data[i]['price'],
                'start_record': data[i-1],
                'end_record': data[i]
            })
            
            duration_minutes = time_diff_seconds / 60
            print(f"   📍 Gap #{len(gaps)}: {duration_minutes:.1f} min gap from {prev_time} to {current_time}")
            print(f"      Price: ${data[i-1]['price']} → ${data[i]['price']}")
    
    return gaps

def create_interpolated_points(gap, interval_seconds=INTERPOLATION_INTERVAL_SECONDS):
    """Create interpolated price points to fill a gap"""
    interpolated_points = []
    
    start_time = gap['start_time']
    end_time = gap['end_time']
    start_price = gap['start_price']
    end_price = gap['end_price']
    
    # Calculate how many points to create
    total_seconds = (end_time - start_time).total_seconds()
    num_points = int(total_seconds / interval_seconds) - 1  # Exclude start/end points
    
    if num_points <= 0:
        return interpolated_points
    
    print(f"      🔧 Creating {num_points} interpolated points...")
    
    for i in range(1, num_points + 1):
        # Linear interpolation
        progress = i / (num_points + 1)
        interpolated_price = start_price + (end_price - start_price) * progress
        
        # Add small random variation if enabled
        if ADD_RANDOM_VARIATION:
            price_range = abs(end_price - start_price)
            if price_range == 0:
                price_range = start_price  # Use start price as reference if no movement
            
            variation = np.random.uniform(-RANDOM_VARIATION_PERCENT, RANDOM_VARIATION_PERCENT)
            price_adjustment = price_range * variation
            interpolated_price += price_adjustment
        
        # Create timestamp
        interpolated_time = start_time + timedelta(seconds=i * interval_seconds)
        
        # Create record matching original format
        interpolated_point = {
            'timestamp': interpolated_time.isoformat(),
            'price': round(interpolated_price, 6),  # Preserve precision
            'gap_filled': True  # Mark as interpolated
        }
        
        interpolated_points.append(interpolated_point)
    
    return interpolated_points

def fill_all_gaps(data):
    """Fill all detected gaps with interpolated points"""
    print("🚀 Starting gap filling process...")
    
    # Detect all gaps
    gaps = detect_gaps(data)
    
    if not gaps:
        print("✅ No gaps detected - data is already continuous!")
        return data
    
    print(f"\n🔧 Found {len(gaps)} gaps to fill")
    
    # Create new data list with gaps filled
    filled_data = []
    last_processed_index = 0
    total_points_added = 0
    
    for gap_num, gap in enumerate(gaps, 1):
        print(f"\n📝 Processing gap {gap_num}/{len(gaps)}:")
        print(f"   Duration: {gap['duration_seconds']/60:.1f} minutes")
        
        # Add all records up to this gap
        filled_data.extend(data[last_processed_index:gap['index']])
        
        # Create and add interpolated points
        interpolated_points = create_interpolated_points(gap)
        filled_data.extend(interpolated_points)
        total_points_added += len(interpolated_points)
        
        print(f"   ✅ Added {len(interpolated_points)} interpolated points")
        
        # Update last processed index (don't include the gap start record again)
        last_processed_index = gap['index']
    
    # Add remaining records after the last gap
    filled_data.extend(data[last_processed_index:])
    
    print(f"\n🎉 Gap filling complete!")
    print(f"   Original records: {len(data)}")
    print(f"   Interpolated points added: {total_points_added}")
    print(f"   Final records: {len(filled_data)}")
    
    return filled_data

def main():
    """Main gap filling process"""
    print("=" * 50)
    print("🔧 Price Data Gap Filler")
    print("=" * 50)
    
    # Read input file
    try:
        print(f"📖 Reading {INPUT_FILE}...")
        with open(INPUT_FILE, 'r') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            raise ValueError("Input file must contain a list of price records")
        
        if len(data) == 0:
            raise ValueError("Input file is empty")
        
        print(f"✅ Loaded {len(data)} price records")
        
        # Validate data format
        required_fields = ['timestamp', 'price']
        if not all(field in data[0] for field in required_fields):
            raise ValueError(f"Records must contain fields: {required_fields}")
        
    except FileNotFoundError:
        print(f"❌ Error: {INPUT_FILE} not found!")
        return
    except json.JSONDecodeError:
        print(f"❌ Error: {INPUT_FILE} is not valid JSON!")
        return
    except Exception as e:
        print(f"❌ Error reading {INPUT_FILE}: {e}")
        return
    
    # Show configuration
    print(f"\n⚙️  Configuration:")
    print(f"   Max gap threshold: {MAX_GAP_SECONDS} seconds ({MAX_GAP_SECONDS/60:.1f} minutes)")
    print(f"   Interpolation interval: {INTERPOLATION_INTERVAL_SECONDS} seconds")
    print(f"   Random variation: {'✓ Enabled' if ADD_RANDOM_VARIATION else '✗ Disabled'} ({RANDOM_VARIATION_PERCENT*100:.1f}%)")
    
    # Sort data by timestamp to ensure chronological order
    print(f"\n🔄 Sorting data chronologically...")
    data.sort(key=lambda x: pd.to_datetime(x['timestamp']))
    
    # Fill gaps
    filled_data = fill_all_gaps(data)
    
    # Save result
    try:
        print(f"\n💾 Saving filled data to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(filled_data, f, indent=2)
        
        print(f"✅ Successfully saved {len(filled_data)} records to {OUTPUT_FILE}")
        
        # Show summary statistics
        original_gaps = len(detect_gaps(data))
        filled_gaps = len(detect_gaps(filled_data))
        points_added = len(filled_data) - len(data)
        
        print(f"\n📊 Summary:")
        print(f"   Original gaps: {original_gaps}")
        print(f"   Remaining gaps: {filled_gaps}")
        print(f"   Points added: {points_added}")
        print(f"   Gap fill success: {((original_gaps - filled_gaps) / max(original_gaps, 1) * 100):.1f}%")
        
        if filled_gaps > 0:
            print(f"   ⚠️  Note: {filled_gaps} gaps remain (smaller than {MAX_GAP_SECONDS} second threshold)")
        
    except Exception as e:
        print(f"❌ Error saving {OUTPUT_FILE}: {e}")
        return
    
    print(f"\n🎯 Gap filling complete! Check {OUTPUT_FILE} for results.")

if __name__ == "__main__":
    main()