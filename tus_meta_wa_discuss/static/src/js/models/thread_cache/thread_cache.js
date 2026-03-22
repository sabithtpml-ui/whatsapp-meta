/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { attr, many, one } from '@mail/model/model_field';


registerPatch({
    name: 'ThreadCache',
    fields: {
        orderedNonEmptyMessages: {
            compute() {
                if(this.thread.isWaMsgs && !this.thread.isChatterWa && this.thread.channel && this.thread.channel.channel_type == 'chat' && this.thread.channel.whatsapp_channel){
                    return this.orderedMessages.filter(message => !message.isEmpty && message.message_type=='wa_msgs');
                }
                else{
                    return this.orderedMessages.filter(message => !message.isEmpty);
                }
            }

            },
        }
});
