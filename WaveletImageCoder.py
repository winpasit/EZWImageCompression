from bitarray import bitarray
import numpy as np
import utils
from zerotree import ZeroTreeDecoder, ZeroTreeEncoder, ZeroTreeScan
import pywt

SOI_MARKER = bytes.fromhex("FFD8") # Start of Image
SOS_MARKER = bytes.fromhex("FFDA") # Start of Scan
EOI_MARKER = bytes.fromhex("FFDC") # End of Image

WAVELET = "db2"

class WaveletImageEncoder():
    def __init__(self, max_passes):
        self.max_passes = max_passes

    def encode(self, image, filename):
        M, N = image.shape[:2]

        with open(filename, 'wb') as fh:
            # Write the header
            fh.write(SOI_MARKER)

            fh.write(M.to_bytes(2, "big"))
            fh.write(N.to_bytes(2, "big"))

            image = image.astype(np.float64)

            encoders = self.build_encoders(image)
            for enc in encoders:
                fh.write(int(enc.start_thresh).to_bytes(2, 'big'))

            encoders = [iter(enc) for enc in encoders]

            i = 0
            writes = float('inf')
            
            while writes != 0 and i < self.max_passes:
                writes = 0
                for enc_iter in encoders:
                    fh.write(SOS_MARKER)
                    scan = next(enc_iter, None)
                    if scan is not None:
                        scan.tofile(fh)
                        writes += 1
                i += 1

            fh.write(EOI_MARKER)

    def build_encoders(self, image):
        ycbcr = utils.RGB2YCbCr(image)
        encoders = [] 
        M, N = image.shape[:2]
        for i in range(3):
            channel = ycbcr[:, :, i] if i == 0 else utils.resize(ycbcr[:, :, i], M // 2, N // 2)
            encoders.append(ZeroTreeEncoder(channel, WAVELET))

        return encoders

class WaveletImageDecoder():
    def decode(self, filename):
        with open(filename, 'rb') as fh:
            soi = fh.read(2)
            if soi != SOI_MARKER:
                raise Exception("Start of Image marker not found!")
            
            M = int.from_bytes(fh.read(2), "big")
            N = int.from_bytes(fh.read(2), "big")

            thresholds = [int.from_bytes(fh.read(2), 'big') for _ in range(3)]
            decoders = self.build_decoders(M, N, thresholds)

            cursor = fh.read(2)
            if cursor != SOS_MARKER:
                raise Exception("Scan's not found!")

            isDominant = True
            while cursor != EOI_MARKER:
                for i, dec in enumerate(decoders):
                    ba = bitarray()

                    cursor = fh.read(2)
                    while cursor != SOS_MARKER and not (cursor == EOI_MARKER and i == 2):
                        ba.frombytes(cursor)
                        cursor = fh.read(2)

                    if len(ba) != 0:
                        scan = ZeroTreeScan.from_bits(ba, isDominant)
                        dec.process(scan)

                isDominant = not isDominant
                
            image = np.zeros((M, N, 3))
            for i, dec in enumerate(decoders):
                image[:, :, i] = dec.getImage() if i == 0 else utils.resize(dec.getImage(), M, N)

        return utils.YCbCr2RGB(image).astype('uint8')

    def build_decoders(self, M, N, thresholds):
        decoders = []
        for i in range(3):
            max_thresh = thresholds[i]
            if i == 0:
                decoders.append(ZeroTreeDecoder(M, N, max_thresh, WAVELET))
            else:
                decoders.append(ZeroTreeDecoder(M // 2, N // 2, max_thresh, WAVELET))
        return decoders