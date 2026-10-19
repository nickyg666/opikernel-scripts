/* vulkan_clear.c — minimal VkCmdClearColorImage to exercise mesa's transfer path.
 * Build: gcc -O1 -o vulkan_clear vulkan_clear.c -lvulkan
 * Run with the powervr ICD: VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/powervr_mesa_icd.aarch64.json
 * or the system-wide ICD (no env needed if powervr is the only ICD).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define CHK(x) do { VkResult r = (x); if (r != VK_SUCCESS) { \
   fprintf(stderr, "FAIL %s -> %d at line %d\n", #x, r, __LINE__); exit(1); } } while (0)

int main(void)
{
   VkInstance inst;
   VkApplicationInfo app = { .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
      .apiVersion = VK_API_VERSION_1_0 };
   VkInstanceCreateInfo ici = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
      .pApplicationInfo = &app };
   CHK(vkCreateInstance(&ici, NULL, &inst));

   uint32_t npd = 0;
   CHK(vkEnumeratePhysicalDevices(inst, &npd, NULL));
   if (!npd) { fprintf(stderr, "no physical devices\n"); return 1; }
   VkPhysicalDevice *pds = calloc(npd, sizeof(*pds));
   CHK(vkEnumeratePhysicalDevices(inst, &npd, pds));
   VkPhysicalDevice pd = pds[0];
   VkPhysicalDeviceProperties props;
   vkGetPhysicalDeviceProperties(pd, &props);
   printf("GPU: %s\n", props.deviceName);

   uint32_t nq = 0;
   vkGetPhysicalDeviceQueueFamilyProperties(pd, &nq, NULL);
   VkQueueFamilyProperties *qf = calloc(nq, sizeof(*qf));
   vkGetPhysicalDeviceQueueFamilyProperties(pd, &nq, qf);
   int tq = -1;
   for (uint32_t i = 0; i < nq; i++) {
      if (qf[i].queueFlags & VK_QUEUE_TRANSFER_BIT) { tq = (int)i; break; }
   }
   if (tq < 0) { fprintf(stderr, "no transfer queue\n"); return 1; }

   const float prio = 1.0f;
   VkDeviceQueueCreateInfo dq = { .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
      .queueFamilyIndex = (uint32_t)tq, .queueCount = 1, .pQueuePriorities = &prio };
   VkDeviceCreateInfo dci = { .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
      .queueCreateInfoCount = 1, .pQueueCreateInfos = &dq };
   VkDevice dev;
   CHK(vkCreateDevice(pd, &dci, NULL, &dev));
   VkQueue queue;
   vkGetDeviceQueue(dev, (uint32_t)tq, 0, &queue);

   /* 128x128 RGBA8 image, transfer-dst. */
   VkImageCreateInfo img = { .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
      .imageType = VK_IMAGE_TYPE_2D, .format = VK_FORMAT_R8G8B8A8_UNORM,
      .extent = { 128, 128, 1 }, .mipLevels = 1, .arrayLayers = 1,
      .samples = VK_SAMPLE_COUNT_1_BIT,
      .tiling = VK_IMAGE_TILING_OPTIMAL,
      .usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT,
      .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED };
   VkImage image;
   CHK(vkCreateImage(dev, &img, NULL, &image));

   VkMemoryRequirements mr;
   vkGetImageMemoryRequirements(dev, image, &mr);
   VkMemoryAllocateInfo mai = { .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize = mr.size };
   /* Find host-visible memory (need readback later; any type for now). */
   VkPhysicalDeviceMemoryProperties mp;
   vkGetPhysicalDeviceMemoryProperties(pd, &mp);
   uint32_t mt = 0xFFFFFFFF;
   for (uint32_t i = 0; i < mp.memoryTypeCount; i++) {
      if (mr.memoryTypeBits & (1u << i)) { mt = i; break; }
   }
   mai.memoryTypeIndex = mt;
   VkDeviceMemory mem;
   CHK(vkAllocateMemory(dev, &mai, NULL, &mem));
   CHK(vkBindImageMemory(dev, image, mem, 0));

   VkCommandPool cp;
   VkCommandPoolCreateInfo cpci = { .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
      .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
      .queueFamilyIndex = (uint32_t)tq };
   CHK(vkCreateCommandPool(dev, &cpci, NULL, &cp));
   VkCommandBuffer cb;
   VkCommandBufferAllocateInfo cbai = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
      .commandPool = cp, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1 };
   CHK(vkAllocateCommandBuffers(dev, &cbai, &cb));

   VkCommandBufferBeginInfo cbb = { .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
   CHK(vkBeginCommandBuffer(cb, &cbb));

   VkImageMemoryBarrier b1 = { .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
      .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = image,
      .subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 } };
   vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                       VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &b1);

   VkClearColorValue cc = { .float32 = { 1.0f, 0.0f, 0.0f, 1.0f } };
   VkImageSubresourceRange range = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
   vkCmdClearColorImage(cb, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &cc, 1, &range);

   VkImageMemoryBarrier b2 = { .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .newLayout = VK_IMAGE_LAYOUT_GENERAL,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = image,
      .subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 } };
   vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT,
                       VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, NULL, 0, NULL, 1, &b2);

   CHK(vkEndCommandBuffer(cb));

   VkSubmitInfo si = { .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
      .commandBufferCount = 1, .pCommandBuffers = &cb };
   CHK(vkQueueSubmit(queue, 1, &si, VK_NULL_HANDLE));
   CHK(vkQueueWaitIdle(queue));

   printf("VK-CLEAR-DONE\n");
   return 0;
}
