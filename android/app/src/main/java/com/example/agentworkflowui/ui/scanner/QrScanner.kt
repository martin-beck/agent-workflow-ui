package com.example.agentworkflowui.ui.scanner

import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage

@Composable
@androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
fun QrScanner(onPayload: (String) -> Unit, modifier: Modifier = Modifier) {
  val owner = LocalLifecycleOwner.current
  AndroidView(modifier = modifier, factory = { context ->
    val view = PreviewView(context)
    val providerFuture = ProcessCameraProvider.getInstance(context)
    providerFuture.addListener({
      val provider = providerFuture.get()
      val preview = Preview.Builder().build().also { it.surfaceProvider = view.surfaceProvider }
      val analyzer = ImageAnalysis.Builder().setTargetResolution(Size(1280, 720))
        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
      val scanner = BarcodeScanning.getClient()
      analyzer.setAnalyzer(ContextCompat.getMainExecutor(context)) { proxy ->
        val image = proxy.image
        if (image == null) { proxy.close(); return@setAnalyzer }
        scanner.process(InputImage.fromMediaImage(image, proxy.imageInfo.rotationDegrees))
          .addOnSuccessListener { codes -> codes.firstOrNull { it.rawValue != null }?.rawValue?.let(onPayload) }
          .addOnCompleteListener { proxy.close() }
      }
      provider.unbindAll()
      provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analyzer)
    }, ContextCompat.getMainExecutor(context))
    view
  })
}
