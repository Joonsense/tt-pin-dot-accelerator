# Example: handwritten digit classifier layer on the chip

One fully connected layer (64 pixels → 10 classes) of an INT8-quantized logistic regression,
computed with the chip's dot products. Each class score is a length-64 dot product; on the N=8 chip
the host driver splits it into 8 chunks and sets CHAIN on all but the last (`pin_client.long_dot`).
The host adds the bias and takes the argmax.

| | Accuracy (360 test images) |
|---|---|
| float (scikit-learn) | 95.83% |
| INT8, Python | 95.83% |
| **INT8, chip RTL (cocotb + host driver)** | **95.83%**, all 3,600 dot products bit-identical to Python |

Chip time: 482,400 clocks for 360 images (134 clocks per length-64 dot product), about 9.6 ms at 50 MHz.
This is the chip side only; a real host must feed one byte per clock to reach it (see `host/`).

Data: scikit-learn `load_digits` (UCI Optical Recognition of Handwritten Digits, CC BY 4.0), 20% stratified
test split, `random_state=0`. Pixels 0..16 are scaled by 4 (max |dot| stays below the 20-bit saturation point).

Files:
- `train.py`: train and quantize (needs numpy and scikit-learn), writes `digits.json`
- `digits_chip.py`: cocotb test that runs the layer on the chip and checks every dot product
- `digits.json`: quantized weights, test inputs, expected dot products and labels
