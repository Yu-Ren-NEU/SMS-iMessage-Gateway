#import <Foundation/Foundation.h>
int main(void) {
    @autoreleasepool {
        NSMutableData *data = [NSMutableData data];
        unsigned char buffer[4096];
        size_t count;
        while ((count = fread(buffer, 1, sizeof(buffer), stdin)) > 0) {
            [data appendBytes:buffer length:count];
        }
        @try {
            id value = [NSUnarchiver unarchiveObjectWithData:data];
            NSString *text = nil;
            if ([value isKindOfClass:[NSAttributedString class]]) text = [value string];
            else if ([value isKindOfClass:[NSString class]]) text = value;
            if (!text) return 2;
            fputs([text UTF8String], stdout);
            return 0;
        } @catch (NSException *exception) {
            return 3;
        }
    }
}
