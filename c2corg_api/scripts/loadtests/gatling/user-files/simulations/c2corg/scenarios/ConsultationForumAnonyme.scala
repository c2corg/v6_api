package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationForumAnonyme extends Simulation {

        val httpProtocol = http
                .inferHtmlResources(C2corgConf.black_list, WhiteList())
                .acceptHeader("application/json, text/javascript, */*; q=0.01")
                .acceptEncodingHeader("gzip, deflate")

        val scn = scenario("ConsultationForumAnonyme")
                .exec(Forum.init)
                .pause(1)
                .exec(Forum.open)
                .pause(6)
                .exec(Forum.scroll)
                .pause(8)
                .exec(Forum.scroll)
                .pause(1)
                .exec(Topic.open)
                .pause(24)
                .exec(Topic.scroll)

        setUp(scn.inject(rampUsers(C2corgConf.num_users) over (C2corgConf.ramp_time_seconds seconds))).protocols(httpProtocol)
}
